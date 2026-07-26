"""
The pieces that need no server: text cleaning, media typing, percentage
clamping, and the database hot-reload machinery.
"""

import asyncio
import contextlib
import os
import sqlite3

import pytest

from app import main
from app.main import _clamp_pct, _media_type, clean_txt


def test_clean_txt_strips_specials_and_case():
    assert clean_txt("  ABC %# ^def & lol  ") == "abc def lol"
    assert clean_txt("already clean") == "already clean"
    assert clean_txt("UPPER") == "upper"


def test_clean_txt_keeps_digits():
    # Show ids arrive through here, so digits and the tt prefix have to survive.
    assert clean_txt("Star Trek: Voyager [1995-2001] = tt0112178") == (
        "star trek voyager 1995 2001 tt0112178"
    )


@pytest.mark.parametrize(
    "raw", ["  ABC %# ^def & lol  ", "!!!", "", "Mixed 123 CASE!!", "tt0112178"]
)
def test_clean_txt_is_idempotent(raw):
    "The docstring promises it, and /search calls it twice on the way in."
    once = clean_txt(raw)
    assert clean_txt(once) == once


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "%^&*", "----"])
def test_clean_txt_reduces_contentless_input_to_empty(raw):
    assert clean_txt(raw) == ""


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://v.redd.it/abc/DASH_720.mp4", "video"),
        ("https://i.redd.it/abc.jpg", "image"),
        ("https://i.redd.it/abc.png", "image"),
        ("https://i.redd.it/abc.gif", "image"),
        # No extension to guess from: the templates render everything that is
        # not a video as an image, so that is the safe answer.
        ("https://www.reddit.com/gallery/abc", "image"),
        ("", "image"),
        (None, "image"),
    ],
)
def test_media_type(url, expected):
    assert _media_type(url) == expected


@pytest.mark.parametrize(
    "given, expected", [(20, 20), (1, 1), (100, 100), (0, 1), (-5, 1), (500, 100)]
)
def test_clamp_pct(given, expected):
    "Percentages come off the url, where 0 and 500 are just as expressible as 20."
    assert _clamp_pct(given) == expected


async def test_search_with_no_usable_terms_skips_the_query():
    """
    An empty box means no results, not an fts5 syntax error.

    No database is opened here on purpose: returning early is the behaviour
    under test, and it used to be a 500.
    """
    assert await main.get_search_results_given_search_str("") == []
    assert await main.get_search_results_given_search_str("   ") == []
    assert await main.get_search_results_given_search_str("!!!") == []


# ---------------------------------------------------------------------------
# Hot reload of a swapped-out database file
# ---------------------------------------------------------------------------


def _write_db(path, value):
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("create table if not exists t (v text)")
        conn.execute("delete from t")
        conn.execute("insert into t values (?)", (value,))
    conn.close()


async def _read_value(conn):
    async with conn.execute("select v from t") as cursor:
        return (await cursor.fetchone())[0]


def test_get_mtime_of_missing_file_is_none(tmp_path):
    assert main._get_mtime(str(tmp_path / "nope.db")) is None
    _write_db(tmp_path / "there.db", "x")
    assert main._get_mtime(str(tmp_path / "there.db")) is not None


async def test_delayed_close_closes_the_connection(tmp_path):
    path = tmp_path / "grace.db"
    _write_db(path, "first")
    conn = await main.open_db(str(path))
    await main._delayed_close(conn, delay=0)
    with pytest.raises(Exception):
        await _read_value(conn)


async def test_reload_db_swaps_in_the_new_file_and_retires_the_old(
    tmp_path, monkeypatch
):
    """
    An open connection follows the inode, not the path.

    cron/refresh_imdb_data.sh builds a fresh imdb.db and mv's it over the old
    one, so without a reload the process keeps serving the unlinked file
    forever — that is the whole reason this machinery exists.
    """
    path = tmp_path / "swap.db"
    _write_db(path, "first")
    stale = await main.open_db(str(path))
    monkeypatch.setattr(main, "db", {"swaptest": stale})

    replacement = tmp_path / "swap.db.new"
    _write_db(replacement, "second")
    os.replace(replacement, path)

    # The pre-swap connection is the problem being solved: still "first".
    assert await _read_value(stale) == "first"

    running_before = asyncio.all_tasks()
    await main._reload_db("swaptest", str(path))
    retiring = asyncio.all_tasks() - running_before

    assert main.db["swaptest"] is not stale
    assert await _read_value(main.db["swaptest"]) == "second"
    # The old connection is retired on a delay rather than closed out from
    # under whatever request is still reading it.
    assert len(retiring) == 1
    assert await _read_value(stale) == "first"

    for task in retiring:
        task.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*retiring, return_exceptions=True)
    for conn in (stale, main.db["swaptest"]):
        with contextlib.suppress(Exception):
            await conn.close()


async def test_watcher_picks_up_a_replaced_file(tmp_path, monkeypatch):
    "The poll loop notices a new mtime and reopens without a restart."
    path = tmp_path / "watched.db"
    _write_db(path, "first")

    monkeypatch.setattr(main, "DB_RELOAD_POLL_SECONDS", 0.01)
    monkeypatch.setattr(main, "DB_CLOSE_GRACE_SECONDS", 0)
    monkeypatch.setattr(main, "DB_PATHS", {"watched": str(path)})
    monkeypatch.setattr(main, "db", {"watched": await main.open_db(str(path))})
    monkeypatch.setattr(main, "db_mtimes", {"watched": main._get_mtime(str(path))})

    task = asyncio.create_task(main.watch_and_reload_dbs())
    try:
        replacement = tmp_path / "watched.db.new"
        _write_db(replacement, "second")
        os.replace(replacement, path)
        # Belt and braces: a same-second mtime would leave the poller blind.
        os.utime(path, (main._get_mtime(str(path)) + 10,) * 2)

        async with asyncio.timeout(5):
            while await _read_value(main.db["watched"]) != "second":
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        # CancelledError is a BaseException, so suppress(Exception) sails past it.
        with contextlib.suppress(asyncio.CancelledError):
            await task
        with contextlib.suppress(Exception):
            await main.db["watched"].close()


async def test_watcher_survives_a_missing_file(tmp_path, monkeypatch):
    "A db that is not there yet must not kill the poll loop for the others."
    missing = tmp_path / "never-created.db"
    monkeypatch.setattr(main, "DB_RELOAD_POLL_SECONDS", 0.01)
    monkeypatch.setattr(main, "DB_PATHS", {"missing": str(missing)})
    monkeypatch.setattr(main, "db", {})
    monkeypatch.setattr(main, "db_mtimes", {"missing": None})

    task = asyncio.create_task(main.watch_and_reload_dbs())
    await asyncio.sleep(0.05)
    assert not task.done(), "watcher died on a missing file"
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
