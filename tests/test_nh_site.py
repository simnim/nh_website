import contextlib
import os
import re
import shutil
import socket
import sqlite3
import subprocess as sp
import sys
import tempfile
import time

import pytest
import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, PROJECT_ROOT)
from app.main import DB_PATHS, QS, clean_txt, open_db  # noqa


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_until_serving(proc, address, timeout=60):
    "True once the port actually answers; False if uvicorn died or never came up."
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            # Any response at all proves the socket is accepting; the status
            # code is the individual tests' business.
            requests.get(f"{address}/index", timeout=2)
            return True
        except requests.RequestException:
            time.sleep(0.25)
    return False


@pytest.fixture(scope="session")
def app_server():
    """
    Base URL of a uvicorn serving this app, one per test session.

    Readiness is a real request against the port rather than uvicorn's
    "Application startup complete" log line: that line lands a beat before the
    socket starts accepting, so waiting on it races the first request and the
    tests fail with a connection refused that has nothing to do with the app.

    The port is whatever the OS hands out, so a dev server already sitting on
    5555 (scripts/dev.sh) neither steals the requests nor blocks the bind.
    """
    port = _free_port()
    address = f"http://127.0.0.1:{port}"
    # A file rather than a pipe: nothing drains it during the session, and a
    # full pipe buffer would wedge the server mid-suite.
    log = tempfile.TemporaryFile()
    proc = sp.Popen(
        ["uvicorn", "app.main:app", "--port", str(port)],
        stdout=log,
        stderr=sp.STDOUT,
        cwd=PROJECT_ROOT,
    )

    if not _wait_until_serving(proc, address):
        proc.kill()
        proc.wait()
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
        log.close()
        raise RuntimeError(f"uvicorn did not start on {address}:\n{output}")

    yield address

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except sp.TimeoutExpired:
        proc.kill()
        proc.wait()
    log.close()


def _unpopulated_reason(db_key, *required_tables):
    """
    Why `db_key` cannot answer queries yet, or None if it can.

    Only imdb.db is rebuilt by cron on a stock checkout; top_cat.db and
    top-books.db are populated by scrapers that do not run everywhere, and
    start life as empty files.
    """
    path = os.path.expanduser(DB_PATHS[db_key])
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return f"{DB_PATHS[db_key]} is empty — that data is not loaded here"
    with contextlib.closing(sqlite3.connect(path)) as conn:
        present = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
    missing = sorted(set(required_tables) - present)
    if missing:
        return f"{DB_PATHS[db_key]} has no {', '.join(missing)} table(s)"
    return None


def _skip_unless_populated(db_key, *required_tables):
    reason = _unpopulated_reason(db_key, *required_tables)
    if reason:
        pytest.skip(reason)


def _make_driver(user_agent=None):
    """
    A headless driver built from whatever browser this machine already has.

    Selenium Manager cannot download drivers for linux/aarch64 (this site's
    usual home is a Raspberry Pi), so auto-provisioning is not an option —
    find the system chromedriver/geckodriver instead, and skip if neither
    browser is installed rather than failing the suite over the environment.
    """
    problems = []

    chromedriver = shutil.which("chromedriver")
    chrome = next(
        (
            path
            for path in map(
                shutil.which, ("chromium", "chromium-browser", "google-chrome")
            )
            if path
        ),
        None,
    )
    if chromedriver and chrome:
        options = webdriver.ChromeOptions()
        options.binary_location = chrome
        for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage"):
            options.add_argument(arg)
        if user_agent:
            options.add_argument(f"--user-agent={user_agent}")
        try:
            return webdriver.Chrome(
                service=webdriver.ChromeService(executable_path=chromedriver),
                options=options,
            )
        except WebDriverException as err:
            problems.append(f"chrome: {err}")
    else:
        problems.append("chrome: no chromedriver/chromium on PATH")

    geckodriver = shutil.which("geckodriver")
    if geckodriver:
        options = webdriver.FirefoxOptions()
        options.add_argument("-headless")
        if user_agent:
            options.set_preference("general.useragent.override", user_agent)
        try:
            return webdriver.Firefox(
                service=webdriver.FirefoxService(executable_path=geckodriver),
                options=options,
            )
        except WebDriverException as err:
            problems.append(f"firefox: {err}")
    else:
        problems.append("firefox: no geckodriver on PATH")

    pytest.skip("no usable webdriver — " + "; ".join(problems))


@pytest.fixture
def browser():
    "Headless desktop browser, quit at the end of the test even on failure."
    drivers = []

    def make(user_agent=None, size=(1280, 900)):
        driver = _make_driver(user_agent=user_agent)
        driver.set_window_size(*size)
        drivers.append(driver)
        return driver

    yield make

    for driver in drivers:
        with contextlib.suppress(Exception):
            driver.quit()


@pytest.fixture
async def cat_conn():
    _skip_unless_populated("cat", "post", "top_post")
    conn = await open_db(DB_PATHS["cat"])
    yield conn
    await conn.close()


@pytest.fixture
async def tv_conn():
    _skip_unless_populated("tv", "basics", "episode", "ratings")
    conn = await open_db(DB_PATHS["tv"])
    yield conn
    await conn.close()


def test_runs_at_all(app_server):
    # Reaching here means the fixture already got a response out of uvicorn;
    # confirm it is this app answering and not something else on the port.
    req = requests.get(f"{app_server}/index", timeout=10)
    assert req.ok and "<html" in req.text.lower()


def test_index(app_server):
    req = requests.get(app_server)
    # Make sure the index page loads and that it advertises my github
    assert req.ok and "https://github.com/simnim/top-cat" in req.text


def test_top_cat(app_server):
    _skip_unless_populated("cat", "post", "top_post")
    req = requests.get(f"{app_server}/top/cat")
    # Load top/cat and check that we got some cats
    assert req.ok and len(re.findall("<hr>", req.text)) > 2


async def test_get_posts_for_hash(cat_conn):
    media_hash = "d205ee2bdc30ba281bd2e696cd18a6e26b2bc697"
    posts = [
        row
        async for row in QS.topcat.get_posts_for_hash(
            cat_conn, media_hash=media_hash, ts_ins=None
        )
    ]
    assert len(posts) > 0
    assert all(p["media_hash"] == media_hash for p in posts)


async def test_episodes_db_queries(tv_conn):
    # Star Trek: Voyager tt0112178
    voyager_id = 112178
    show = await QS.episodes.get_basic_show_info(tv_conn, imdb_show_id=voyager_id)
    assert show["primaryTitle"] == "Star Trek: Voyager"
    episodes = [
        row
        async for row in QS.episodes.get_top_episodes_for_show(
            tv_conn, imdb_show_id=voyager_id, max_rank_pct=20
        )
    ]
    assert len(episodes) > 0
    assert any(ep["is_top_episode"] == 1 for ep in episodes)
    assert any(ep["is_top_episode"] == 0 for ep in episodes)
    assert all(ep["percentile"] >= 80 for ep in episodes if ep["is_top_episode"] == 1)
    assert all(ep["percentile"] < 80 for ep in episodes if ep["is_top_episode"] == 0)


def test_clean_txt():
    assert clean_txt("  ABC %# ^def & lol  ") == "abc def lol"
    assert clean_txt("already clean") == "already clean"
    assert clean_txt("UPPER") == "upper"


def test_episodes_direct_show(app_server):
    # Star Trek: Voyager tt0112178
    req = requests.get(f"{app_server}/episodes/tt0112178")
    assert req.ok and "Star Trek: Voyager" in req.text
    assert "data-percentile=" in req.text
    assert "data-threshold=" in req.text
    # Percentile bars render server-side, so they are in the raw HTML
    assert "pct-fill" in req.text
    assert "pct-cutoff" in req.text


def test_favicon(app_server):
    req = requests.get(f"{app_server}/favicon.ico")
    assert req.ok and req.headers["Content-Type"].startswith("image/")


def test_episodes_index(app_server):
    req = requests.get(f"{app_server}/episodes")
    assert req.ok and "Show Name Search" in req.text


def test_books(app_server):
    _skip_unless_populated("books", "books", "top_books", "cache_book_categories")
    req = requests.get(f"{app_server}/books")
    assert req.ok and "Books" in req.text


def test_search_returns_results(app_server):
    req = requests.get(f"{app_server}/search", params={"term": "trek voyager"})
    assert req.ok and any("Voyager" in r for r in req.json())


def test_top_episodes_search_and_display_shows(app_server, browser):
    """
    simulate loading the top episodes page and searching for "trek voyager"
    inspired by from https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Headless_mode
    """
    driver = browser()

    # Wait until an element is visible on the page
    wait = WebDriverWait(driver, timeout=20)

    driver.get(f"{app_server}/episodes")
    # wait until episode search is available, then do search
    (
        wait.until(
            EC.visibility_of_element_located((By.NAME, "imdb_show_id"))
        ).send_keys("trek voyager")
    )
    # Click the first thing
    (wait.until(EC.visibility_of_element_located((By.ID, "ui-id-1"))).click())
    # Hit submit
    (wait.until(EC.visibility_of_element_located((By.NAME, "submit"))).click())
    # Submitting POSTs, redirects and loads a fresh document; reading
    # page_source before the results land yields an empty body.
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))
    page_source = driver.page_source
    assert (
        "<td> Star Trek: Voyager </td>" in page_source
        and "<td> Eye of the Needle </td>" in page_source
    )


# Geometry of the frozen header, read straight off the element that sticks.
# The th carries position:sticky (collapsed borders leave the tr unable to), so
# the tr's rect would not move even while the header is pinned.
_HEADER_PROBE = """
    const table = document.getElementById('episodes-table');
    const head = table.querySelector('thead');
    const th = head.querySelector('th');
    const cell = th.getBoundingClientRect();
    const rect = table.getBoundingClientRect();
    return {
        thTop: Math.round(cell.top),
        tableTop: Math.round(rect.top),
        tableBottom: Math.round(rect.bottom),
        stuck: head.classList.contains('is-stuck'),
        position: getComputedStyle(th).position,
        opaque: getComputedStyle(th).backgroundColor,
    };
"""


@pytest.mark.parametrize(
    "user_agent, size",
    [
        (None, (1280, 900)),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
            " (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            (390, 844),
        ),
    ],
    ids=["desktop", "mobile"],
)
def test_top_episodes_header_freezes_while_scrolling(
    app_server, browser, user_agent, size
):
    """
    The Top Episodes header row behaves like an Excel frozen header: it rides at
    the top of the window for as long as its table is on screen.
    """
    driver = browser(user_agent=user_agent, size=size)
    wait = WebDriverWait(driver, timeout=20)
    driver.get(f"{app_server}/episodes/tt0112178/30")
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))

    before = driver.execute_script(_HEADER_PROBE)
    assert before["position"] == "sticky"
    # Opaque, or the coloured rows would scroll straight through the header.
    assert before["opaque"] != "rgba(0, 0, 0, 0)"
    # Nothing pinned yet, and no shadow claiming otherwise.
    assert before["thTop"] > 0 and not before["stuck"]

    # Scroll deep enough that the table straddles the top of the viewport.
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    wait.until(lambda d: d.execute_script(_HEADER_PROBE)["stuck"])

    after = driver.execute_script(_HEADER_PROBE)
    assert (
        after["tableTop"] < 0 < after["tableBottom"]
    ), "table should span the top edge"
    assert after["thTop"] == 0, "header should be pinned to the top of the window"
    # It has to paint over the rows passing underneath, not behind them.
    assert (
        driver.execute_script(
            "return document.elementFromPoint(window.innerWidth / 2, 8).tagName"
        )
        == "TH"
    )

    # Back at the top, the header sits back down with its table.
    driver.execute_script("window.scrollTo(0, 0);")
    wait.until(lambda d: not d.execute_script(_HEADER_PROBE)["stuck"])
    assert driver.execute_script(_HEADER_PROBE)["thTop"] > 0
