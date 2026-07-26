"""
Shared fixtures.

Three ways to drive the app, cheapest first:

* `client`   — in-process TestClient over the synthetic databases. Default for
               anything that is really about a route, a query or a template.
* `browser`  — headless selenium against `app_server`, for the parts that only
               exist once javascript runs.
* `*_conn`   — the real ~/.nh-website-data databases, skipped when they are not
               loaded. Only for asserting things about the real data.
"""

import contextlib
import os
import shutil
import socket
import sqlite3
import subprocess as sp
import sys
import tempfile
import time

import aiosql
import pytest
import requests
from fastapi.testclient import TestClient
from selenium import webdriver
from selenium.common.exceptions import WebDriverException

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, TESTS_DIR)
import fixture_data  # noqa: E402

from app import main  # noqa: E402
from app.main import DB_PATHS  # noqa: E402

# A user-agent from the list MobileMiddleware matches on, and a phone-sized
# window to go with it.
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MOBILE_SIZE = (390, 844)
DESKTOP_SIZE = (1280, 900)


@pytest.fixture(scope="session")
def fixture_data_dir(tmp_path_factory):
    "The three synthetic databases, built once for the whole session."
    return fixture_data.build_all(tmp_path_factory.mktemp("nh-website-data"))


@pytest.fixture
def client(fixture_data_dir, monkeypatch):
    """
    TestClient wired to the synthetic databases.

    The paths are patched rather than the env var because DB_PATHS is built at
    import time and app.main is already imported by the time a test runs.
    """
    for key, name in (
        ("cat", "top_cat.db"),
        ("tv", "imdb.db"),
        ("books", "top-books.db"),
    ):
        monkeypatch.setitem(main.DB_PATHS, key, str(fixture_data_dir / name))
    # Entering the context manager is what runs the lifespan, and the lifespan
    # is what opens the connections.
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def fixture_tv_queries(fixture_data_dir):
    """
    Synchronous handle on the synthetic imdb.db.

    Tests derive their expected percentiles and top/not-top counts by running
    the app's own queries here, so a page assertion cannot drift from the sql
    it is supposed to be displaying.
    """
    queries = aiosql.from_path(main.THIS_DIR / "sql", "sqlite3", kwargs_only=True)
    conn = sqlite3.connect(fixture_data_dir / "imdb.db")
    conn.row_factory = sqlite3.Row
    yield queries, conn
    conn.close()


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
def app_server(fixture_data_dir):
    """
    Base URL of a uvicorn serving this app, one per test session.

    It reads the synthetic databases via NH_WEBSITE_DATA_DIR, so the browser
    tests below assert against known episodes instead of whatever imdb published
    this week — and they run on a machine that has never loaded the real data.

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
        env={**os.environ, "NH_WEBSITE_DATA_DIR": str(fixture_data_dir)},
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
    Why the real `db_key` cannot answer queries yet, or None if it can.

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


def skip_unless_populated(db_key, *required_tables):
    reason = _unpopulated_reason(db_key, *required_tables)
    if reason:
        pytest.skip(reason)


@pytest.fixture
async def cat_conn():
    "Connection to the real top_cat.db."
    skip_unless_populated("cat", "post", "top_post")
    conn = await main.open_db(DB_PATHS["cat"])
    yield conn
    await conn.close()


@pytest.fixture
async def tv_conn():
    "Connection to the real imdb.db."
    skip_unless_populated("tv", "basics", "episode", "ratings")
    conn = await main.open_db(DB_PATHS["tv"])
    yield conn
    await conn.close()


@pytest.fixture
async def books_conn():
    "Connection to the real top-books.db."
    skip_unless_populated("books", "books", "top_books", "cache_book_categories")
    conn = await main.open_db(DB_PATHS["books"])
    yield conn
    await conn.close()


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
        # So a test can ask whether the page threw anything.
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
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

    def make(user_agent=None, size=DESKTOP_SIZE):
        driver = _make_driver(user_agent=user_agent)
        driver.set_window_size(*size)
        drivers.append(driver)
        return driver

    yield make

    for driver in drivers:
        with contextlib.suppress(Exception):
            driver.quit()
