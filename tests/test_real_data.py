"""
Checks against the real ~/.nh-website-data databases.

Everything else in this suite runs on synthetic data, which proves the app
works but says nothing about whether this week's imdb dump actually loaded. The
tests here are the other half: they assert about the data itself, and skip
where it is not present (top_cat.db and top-books.db come from scrapers that
only run on the live host).
"""

import pytest

from app import main
from app.main import QS

pytestmark = pytest.mark.realdata

# Star Trek: Voyager, tt0112178 — a finished series, so its numbers do not move.
VOYAGER_ID = 112178


async def test_real_imdb_has_show_metadata(tv_conn):
    show = await QS.episodes.get_basic_show_info(tv_conn, imdb_show_id=VOYAGER_ID)
    assert show["primaryTitle"] == "Star Trek: Voyager"
    assert show["startYear"] == 1995
    # Built by add-indexes.sql; the search box and its ordering need both.
    assert show["label"].startswith("Star Trek: Voyager")
    assert show["value"] == "tt0112178"


async def test_real_imdb_percentiles_and_top_flag(tv_conn):
    episodes = [
        row
        async for row in QS.episodes.get_top_episodes_for_show(
            tv_conn, imdb_show_id=VOYAGER_ID, max_rank_pct=20
        )
    ]
    assert len(episodes) > 100, "Voyager ran for seven seasons"
    assert any(ep["is_top_episode"] == 1 for ep in episodes)
    assert any(ep["is_top_episode"] == 0 for ep in episodes)
    assert all(ep["percentile"] >= 80 for ep in episodes if ep["is_top_episode"] == 1)
    assert all(ep["percentile"] < 80 for ep in episodes if ep["is_top_episode"] == 0)
    # Canonical order is what makes the row ids and n/p navigation meaningful.
    numbered = [
        (ep["seasonNumber"], ep["episodeNumber"])
        for ep in episodes
        if ep["seasonNumber"] is not None and ep["episodeNumber"] is not None
    ]
    assert numbered == sorted(numbered)


async def test_real_imdb_seasons_summary(tv_conn):
    seasons = [
        row
        async for row in QS.episodes.get_seasons_summary(
            tv_conn, imdb_show_id=VOYAGER_ID
        )
    ]
    assert len(seasons) >= 7
    assert all(0 <= s["average_percentile"] <= 100 for s in seasons)
    assert all(0 < s["average_rating"] <= 10 for s in seasons)


async def test_real_imdb_full_text_search(tv_conn, monkeypatch):
    "The autocomplete against the real index, including its vote ordering."
    monkeypatch.setitem(main.db, "tv", tv_conn)
    results = await main.get_search_results_given_search_str("trek voyager")
    assert any("Voyager" in label for label in results)
    assert len(results) <= 15  # the query's limit

    ids = await main.get_search_results_given_search_str(
        "trek voyager", return_just_id=True
    )
    assert "tt0112178" in ids


async def test_real_top_cat_posts_for_hash(cat_conn):
    media_hash = "d205ee2bdc30ba281bd2e696cd18a6e26b2bc697"
    posts = [
        row
        async for row in QS.topcat.get_posts_for_hash(
            cat_conn, media_hash=media_hash, ts_ins=None
        )
    ]
    assert len(posts) > 0
    assert all(p["media_hash"] == media_hash for p in posts)


async def test_real_top_cat_recent_posts(cat_conn):
    posts = [
        row async for row in QS.topcat.get_top_posts_for_flask(cat_conn, label="cat")
    ]
    assert 0 < len(posts) <= 10
    assert all(p["media"] for p in posts)
    # The template needs a hash and a timestamp to build the permalink.
    assert all(p["media_hash"] and p["noticed_at"] for p in posts)


async def test_real_books(books_conn):
    categories = [
        row["category"]
        async for row in QS.books.get_categories_for_top_books(books_conn)
    ]
    assert categories
    books = [
        row
        async for row in QS.books.get_top_books_for_category(
            books_conn, category=categories[0]
        )
    ]
    assert 0 < len(books) <= 10
