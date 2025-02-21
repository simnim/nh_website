import os
import re
import subprocess as sp
import sys
import time

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# from selenium.webdriver.common.keys import Keys

LOCALHOST = "127.0.0.1"
TESTING_PORT = 5555


# FIXME: Import from app instead of running this on the cli
@pytest.fixture
def flask_app_server():
    # Run the flask app
    flask_proc = sp.Popen(
        # ["uv", "run", "flask", "run", "-p", str(TESTING_PORT)],
        ["flask", "run", "-p", str(TESTING_PORT)],
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        env=dict(os.environ, FLASK_APP="flask_nh_site.py"),
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    time.sleep(1)
    try:
        flask_stderr_chatter_line = flask_proc.stderr.readline()
        # Try to eat through any flask startup spam / errors
        for i in range(10):
            if (
                flask_stderr_chatter_line.startswith(b" * Tip:")
                or flask_stderr_chatter_line.startswith(b"#")
                or flask_stderr_chatter_line.startswith(b"WARNING")
            ):
                flask_stderr_chatter_line = flask_proc.stderr.readline()
        if b" * Running on http:" in flask_stderr_chatter_line:
            yield flask_proc
        else:
            raise Exception(
                flask_proc.stderr.readline().decode("utf-8").strip().split("\n")[-1]
            )
    except Exception:
        raise
    flask_proc.kill()


def test_runs_at_all(flask_app_server):
    if flask_app_server.poll() is not None:
        print(flask_app_server.stderr.read().decode("utf-8"), file=sys.stderr)
    assert flask_app_server.poll() is None


def test_index(flask_app_server):
    req = requests.get(f"http://{LOCALHOST}:{TESTING_PORT}")
    # Make sure the index page loads and that it advertises my github
    assert req.ok and "https://github.com/simnim/top-cat" in req.text


def test_top_cat(flask_app_server):
    req = requests.get(f"http://{LOCALHOST}:{TESTING_PORT}/top/cat")
    # Load top/cat and check that we got some cats
    assert req.ok and len(re.findall("<hr>", req.text)) > 2


def test_top_episodes_search_and_display_shows(flask_app_server):
    """
    simulate loading the top episodes page and searching for "trek, voyager"
    inspired by from https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Headless_mode
    """
    options = webdriver.FirefoxOptions()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options)

    # Wait until an element is visible on the page
    wait = WebDriverWait(driver, timeout=10)
    # element = wait.until(EC.visibility_of_element_located((By.ID, "exampleId")))
    # print(element.text)

    driver.get(f"http://{LOCALHOST}:{TESTING_PORT}/episodes")
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
