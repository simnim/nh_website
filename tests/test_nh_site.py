import os
import re
import subprocess as sp
import sys

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

TESTING_PORT = 5555
LOCAL_ADDRESS = f"127.0.0.1:{TESTING_PORT}"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, PROJECT_ROOT)
from app.main import QS, clean_txt, open_db  # noqa


@pytest.fixture
def app_server():
    proc = sp.Popen(
        ["uvicorn", "app.main:app", "--port", str(TESTING_PORT)],
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        cwd=PROJECT_ROOT,
    )
    # Wait for uvicorn to report startup complete
    for _ in range(30):
        line = proc.stderr.readline()
        if b"Application startup complete" in line:
            yield proc
            proc.kill()
            return
        if proc.poll() is not None:
            break
    raise Exception("uvicorn did not start: " + proc.stderr.read().decode("utf-8"))


@pytest.fixture
async def cat_conn():
    conn = await open_db("~/.top_cat/db")
    yield conn
    await conn.close()


@pytest.fixture
async def tv_conn():
    conn = await open_db("~/imdb.db")
    yield conn
    await conn.close()


def test_runs_at_all(app_server):
    if app_server.poll() is not None:
        print(app_server.stderr.read().decode("utf-8"), file=sys.stderr)
    assert app_server.poll() is None


def test_index(app_server):
    req = requests.get(f"http://{LOCAL_ADDRESS}")
    # Make sure the index page loads and that it advertises my github
    assert req.ok and "https://github.com/simnim/top-cat" in req.text


def test_top_cat(app_server):
    req = requests.get(f"http://{LOCAL_ADDRESS}/top/cat")
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
    assert all(ep["percentile"] >= 80 for ep in episodes)


def test_clean_txt():
    assert clean_txt("  ABC %# ^def & lol  ") == "abc def lol"
    assert clean_txt("already clean") == "already clean"
    assert clean_txt("UPPER") == "upper"


def test_episodes_direct_show(app_server):
    # Star Trek: Voyager tt0112178
    req = requests.get(f"http://{LOCAL_ADDRESS}/episodes/tt0112178")
    assert req.ok and "Star Trek: Voyager" in req.text


def test_favicon(app_server):
    req = requests.get(f"http://{LOCAL_ADDRESS}/favicon.ico")
    assert req.ok and req.headers["Content-Type"].startswith("image/")


def test_episodes_index(app_server):
    req = requests.get(f"http://{LOCAL_ADDRESS}/episodes")
    assert req.ok and "Show Name Search" in req.text


def test_books(app_server):
    req = requests.get(f"http://{LOCAL_ADDRESS}/books")
    assert req.ok and "Books" in req.text


def test_search_returns_results(app_server):
    req = requests.get(
        f"http://{LOCAL_ADDRESS}/search", params={"term": "trek voyager"}
    )
    assert req.ok and any("Voyager" in r for r in req.json())


def test_top_episodes_search_and_display_shows(app_server):
    """
    simulate loading the top episodes page and searching for "trek voyager"
    inspired by from https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Headless_mode
    """
    options = webdriver.FirefoxOptions()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options)

    # Wait until an element is visible on the page
    wait = WebDriverWait(driver, timeout=20)

    driver.get(f"http://{LOCAL_ADDRESS}/episodes")
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
    page_source = driver.page_source
    driver.quit()
    assert (
        "<td> Star Trek: Voyager </td>" in page_source
        and "<td> Eye of the Needle </td>" in page_source
    )
