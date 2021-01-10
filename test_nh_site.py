import os
import subprocess as sp
import time
from contextlib import contextmanager

import selenium
from selenium.webdriver.common.by import By

# from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as expected


# https://docs.python.org/3/library/contextlib.html
@contextmanager
def flask_app_server():
    # Run the flask app
    flask_proc = sp.Popen(
        ["flask", "run", "-p", "5555"],
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        env=dict(os.environ, FLASK_APP="flask_nh_site.py"),
    )
    time.sleep(1)
    try:
        first_stderr = flask_proc.stderr.readline()
        if b" * Running on http:" in first_stderr:
            yield flask_proc
        else:
            raise Exception(
                flask_proc.stderr.read().decode("utf-8").strip().split("\n")[-1]
            )
    finally:
        flask_proc.kill()


def test_top_episodes_search_and_display_shows():
    # simulate loading the top episodes page
    # type "trek voyager" into the search box
    # select the first menu item (should be the right one)
    # check it loaded the right stuff
    # inspired by from https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Headless_mode
    with flask_app_server():
        options = selenium.webdriver.firefox.options.Options()
        options.add_argument("-headless")
        driver = selenium.webdriver.Firefox(
            executable_path="geckodriver", options=options
        )
        wait = selenium.webdriver.support.wait.WebDriverWait(driver, timeout=10)
        driver.get("http://127.0.0.1:5555/episodes")
        wait.until(
            expected.visibility_of_element_located((By.NAME, "imdb_show_id"))
        ).send_keys("trek voyager")
        wait.until(expected.visibility_of_element_located((By.ID, "ui-id-1"))).click()
        wait.until(expected.visibility_of_element_located((By.NAME, "submit"))).click()
        page_source = driver.page_source
        driver.quit()
        page_source
        assert (
            "<td> Star Trek: Voyager </td>" in page_source
            and "<td> Eye of the Needle </td>" in page_source
        )
