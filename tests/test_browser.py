"""
The parts of Top Episodes that only exist once javascript has run.

Everything here drives the synthetic "Nebula Patrol" (100 episodes, fixed
ratings), so row counts and top/not-top splits are stable and the suite does not
need the real 1.6 GB imdb dump.
"""

import re

import fixture_data
import pytest
from conftest import MOBILE_SIZE, MOBILE_UA
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.browser

SHOW = fixture_data.MAIN_SHOW_TCONST
SHOW_TITLE = fixture_data.MAIN_SHOW_TITLE


def open_show(browser, app_server, path=f"/episodes/{SHOW}/20", **kwargs):
    "A driver parked on an episodes page with the table rendered."
    driver = browser(**kwargs)
    driver.get(f"{app_server}{path}")
    WebDriverWait(driver, timeout=20).until(EC.presence_of_element_located((By.ID, "episodes-table")))
    return driver, WebDriverWait(driver, timeout=20)


def require_jquery(driver):
    """
    The search box, the slider and the presets are all wired up inside
    $(document).ready, and jquery comes from a cdn — without a network there is
    nothing to test rather than something to fail.
    """
    if driver.execute_script("return typeof window.jQuery") == "undefined":
        pytest.skip("jquery did not load — no network for the cdn")


def test_search_finds_a_show_and_renders_its_episodes(app_server, browser):
    "Type, pick from the autocomplete, submit, land on the show."
    driver = browser()
    wait = WebDriverWait(driver, timeout=20)
    driver.get(f"{app_server}/episodes")
    require_jquery(driver)

    wait.until(EC.visibility_of_element_located((By.NAME, "imdb_show_id"))).send_keys("nebula patrol")
    # First suggestion, which is the most-voted match. Addressed by class
    # rather than by the generated ui-id-N, which numbers the menu itself
    # first and so points at the <ul>, not at a row.
    wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "ul.ui-autocomplete li:first-child .ui-menu-item-wrapper"))
    ).click()
    wait.until(EC.visibility_of_element_located((By.NAME, "submit"))).click()
    # Submitting POSTs, redirects and loads a fresh document; reading
    # page_source before the results land yields an empty body.
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))

    assert f"<td> {SHOW_TITLE} </td>" in driver.page_source
    assert f"<td> {SHOW_TITLE} S1E1 </td>" in driver.page_source
    assert SHOW in driver.current_url


def test_search_box_keeps_what_you_searched_for(app_server, browser):
    driver, _wait = open_show(browser, app_server)
    box = driver.find_element(By.NAME, "imdb_show_id")
    assert box.get_attribute("value") == fixture_data.MAIN_SHOW_LABEL


# ---------------------------------------------------------------------------
# Frozen header
# ---------------------------------------------------------------------------

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
    [(None, None), (MOBILE_UA, MOBILE_SIZE)],
    ids=["desktop", "mobile"],
)
def test_top_episodes_header_freezes_while_scrolling(app_server, browser, user_agent, size):
    """
    The Top Episodes header row behaves like an Excel frozen header: it rides at
    the top of the window for as long as its table is on screen.
    """
    kwargs = {"user_agent": user_agent}
    if size:
        kwargs["size"] = size
    driver, wait = open_show(browser, app_server, f"/episodes/{SHOW}/30", **kwargs)

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
    assert after["tableTop"] < 0 < after["tableBottom"], "table should span the top edge"
    assert after["thTop"] == 0, "header should be pinned to the top of the window"
    # It has to paint over the rows passing underneath, not behind them.
    assert driver.execute_script("return document.elementFromPoint(window.innerWidth / 2, 8).tagName") == "TH"

    # Back at the top, the header sits back down with its table.
    driver.execute_script("window.scrollTo(0, 0);")
    wait.until(lambda d: not d.execute_script(_HEADER_PROBE)["stuck"])
    assert driver.execute_script(_HEADER_PROBE)["thTop"] > 0


def test_only_one_header_is_pinned_at_a_time(app_server, browser):
    "Both tables are sticky-head; a sticky element is bounded by its own table."
    driver, wait = open_show(browser, app_server)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    wait.until(lambda d: d.execute_script("return document.querySelectorAll('thead.is-stuck').length") == 1)
    assert driver.execute_script("return document.querySelectorAll('table.sticky-head').length") == 2


# ---------------------------------------------------------------------------
# Hide below the cutoff
# ---------------------------------------------------------------------------

# State of the hide-below-cutoff toggle. offsetParent is null for a
# display:none row, so `visible` is what the reader actually sees rather than
# what the class names claim.
_TOGGLE_PROBE = """
    const table = document.getElementById('episodes-table');
    const btn = document.getElementById('toggle-below');
    const rows = Array.from(table.querySelectorAll('tbody tr[data-percentile]'));
    return {
        hiding: table.classList.contains('hide-below'),
        label: btn ? btn.textContent : null,
        pressed: btn ? btn.getAttribute('aria-pressed') : null,
        total: rows.length,
        below: rows.filter(r => r.classList.contains('below-cutoff')).length,
        visible: rows.filter(r => r.offsetParent !== null).length,
    };
"""


def test_top_episodes_hide_below_cutoff(app_server, browser):
    """
    The button and the h shortcut collapse the table to the top episodes.

    Nothing is persisted, so every load starts with the whole show visible.
    """
    driver, _wait = open_show(browser, app_server)
    body = driver.find_element(By.TAG_NAME, "body")

    before = driver.execute_script(_TOGGLE_PROBE)
    assert before["total"] == fixture_data.MAIN_SHOW_EPISODES
    assert before["below"] > 0, "20% cutoff should leave something to hide"
    assert not before["hiding"] and before["pressed"] == "false"
    assert before["visible"] == before["total"], "a fresh load shows every episode"
    assert before["label"] == f"Hide {before['below']} episodes below the cutoff"

    top_count = before["total"] - before["below"]

    driver.find_element(By.ID, "toggle-below").click()
    hidden = driver.execute_script(_TOGGLE_PROBE)
    assert hidden["hiding"] and hidden["pressed"] == "true"
    assert hidden["visible"] == top_count
    assert hidden["label"] == f"Show all {before['total']} episodes"

    driver.find_element(By.ID, "toggle-below").click()
    assert driver.execute_script(_TOGGLE_PROBE)["visible"] == before["total"]

    # Same toggle from the keyboard.
    body.send_keys("h")
    assert driver.execute_script(_TOGGLE_PROBE)["visible"] == top_count
    body.send_keys("h")
    assert driver.execute_script(_TOGGLE_PROBE)["visible"] == before["total"]

    # Typing a show name with an h in it must not collapse the table.
    box = driver.find_element(By.NAME, "imdb_show_id")
    box.clear()
    box.send_keys("h")
    assert not driver.execute_script(_TOGGLE_PROBE)["hiding"]
    assert box.get_attribute("value") == "h"

    # Marking a below-cutoff episode and then hiding keeps the marker on the
    # row — it comes back where it was — and n still steps to the next top one.
    marked = driver.execute_script("""
        const row = document.querySelector('#episodes-table tbody tr.below-cutoff');
        row.click();
        return row.id;
        """)
    body.send_keys("h")
    assert driver.execute_script("""
        const row = document.querySelector('#episodes-table tbody tr.current-episode');
        return row.classList.contains('below-cutoff') && row.offsetParent === null;
        """), "the marked row is hidden but still marked"
    body.send_keys("n")
    stepped = driver.execute_script("""
        const row = document.querySelector('#episodes-table tbody tr.current-episode');
        return {id: row.id, visible: row.offsetParent !== null};
        """)
    assert stepped["id"] != marked and stepped["visible"]


def test_top_episodes_hide_toggle_absent_with_nothing_to_hide(app_server, browser):
    "At 100% every episode is a top episode, so a hide button would be a lie."
    driver, _wait = open_show(browser, app_server, f"/episodes/{SHOW}/100")

    probe = driver.execute_script(_TOGGLE_PROBE)
    assert probe["below"] == 0 and probe["label"] is None

    driver.find_element(By.TAG_NAME, "body").send_keys("h")
    assert not driver.execute_script(_TOGGLE_PROBE)["hiding"], "h is a no-op here"


# ---------------------------------------------------------------------------
# Place marker and keyboard navigation
# ---------------------------------------------------------------------------

_MARKER_PROBE = """
    const cur = document.querySelector('#episodes-table tbody tr.current-episode');
    const rows = Array.from(
        document.querySelectorAll('#episodes-table tbody tr[data-percentile]'));
    return {
        id: cur ? cur.id : null,
        index: cur ? rows.indexOf(cur) : null,
        isTop: cur ? !cur.classList.contains('below-cutoff') : null,
        marked: document.querySelectorAll('.current-episode').length,
        hash: location.hash,
        path: location.pathname,
    };
"""

_TOP_ROW_IDS = """
    return Array.from(document.querySelectorAll(
        '#episodes-table tbody tr[data-percentile]:not(.below-cutoff)')).map(r => r.id);
"""


def test_clicking_an_episode_marks_your_place_in_the_url(app_server, browser):
    driver, _wait = open_show(browser, app_server)
    assert driver.execute_script(_MARKER_PROBE)["marked"] == 0

    row_id = driver.execute_script(_TOP_ROW_IDS)[3]
    driver.find_element(By.ID, row_id).click()

    marked = driver.execute_script(_MARKER_PROBE)
    assert marked["id"] == row_id and marked["marked"] == 1
    # The hash is the whole point: the place survives closing the browser.
    assert marked["hash"] == f"#{row_id}"

    # Only one row is ever marked.
    other = driver.execute_script(_TOP_ROW_IDS)[7]
    driver.find_element(By.ID, other).click()
    moved = driver.execute_script(_MARKER_PROBE)
    assert moved["id"] == other and moved["marked"] == 1 and moved["hash"] == f"#{other}"


def test_a_marked_place_is_restored_on_reload(app_server, browser):
    driver, wait = open_show(browser, app_server)
    row_id = driver.execute_script(_TOP_ROW_IDS)[5]
    driver.find_element(By.ID, row_id).click()

    driver.get(driver.current_url)
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))
    restored = driver.execute_script(_MARKER_PROBE)
    assert restored["id"] == row_id and restored["hash"] == f"#{row_id}"


def _submit_search(driver, wait, text):
    "Type a show name over whatever is in the box and submit the form."
    box = wait.until(EC.visibility_of_element_located((By.NAME, "imdb_show_id")))
    box.clear()
    box.send_keys(text)
    # The suggestion menu drops over the submit button, and it opens on a delay
    # — so wait for it before dismissing it, or Escape closes nothing and it
    # arrives in time to swallow the click. Escape leaves the typed term in
    # place, which is the lazy path the POST handler resolves by searching.
    menu = (By.CSS_SELECTOR, "ul.ui-autocomplete li")
    wait.until(EC.visibility_of_element_located(menu))
    box.send_keys(Keys.ESCAPE)
    wait.until_not(EC.visibility_of_element_located(menu))
    assert box.get_attribute("value") == text
    driver.find_element(By.NAME, "submit").click()
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))


def test_searching_a_new_show_drops_the_marker(app_server, browser):
    """
    Row ids are s<season>e<episode>, so the hash names a real row on any show.
    The form posts to the current url and the browser copies its fragment onto
    the redirect target, which would open the new show with the old show's
    place marked — on an episode the reader has never seen.
    """
    driver, wait = open_show(browser, app_server)
    require_jquery(driver)
    # A row Redux has too, so an inherited hash would find something to mark.
    driver.find_element(By.ID, "s1e3").click()
    assert driver.execute_script(_MARKER_PROBE)["hash"] == "#s1e3"

    _submit_search(driver, wait, "nebula patrol redux")

    landed = driver.execute_script(_MARKER_PROBE)
    assert fixture_data.REDUX_SHOW_TCONST in driver.current_url, "search should have moved shows"
    assert landed["marked"] == 0 and landed["id"] is None
    assert landed["hash"] == ""
    # The row is still there to be marked; it just is not marked for you.
    assert driver.find_element(By.ID, "s1e3")


def test_resubmitting_the_same_show_keeps_the_marker(app_server, browser):
    "Submitting is also how a typed cutoff is applied, and that is not a move."
    driver, wait = open_show(browser, app_server)
    require_jquery(driver)
    driver.find_element(By.ID, "s1e3").click()

    pct = driver.find_element(By.NAME, "max_rank_pct")
    pct.clear()
    pct.send_keys("50")
    driver.find_element(By.NAME, "submit").click()
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))

    kept = driver.execute_script(_MARKER_PROBE)
    assert kept["path"] == f"/episodes/{SHOW}/50"
    assert kept["id"] == "s1e3" and kept["hash"] == "#s1e3"


def test_n_and_p_step_through_top_episodes_only(app_server, browser):
    driver, _wait = open_show(browser, app_server)
    body = driver.find_element(By.TAG_NAME, "body")
    top_ids = driver.execute_script(_TOP_ROW_IDS)
    assert len(top_ids) > 3, "fixture show should have several top episodes"

    # With nothing marked, n starts at the best-placed top episode.
    body.send_keys("n")
    assert driver.execute_script(_MARKER_PROBE)["id"] == top_ids[0]

    for expected in top_ids[1:4]:
        body.send_keys("n")
        state = driver.execute_script(_MARKER_PROBE)
        assert state["id"] == expected and state["isTop"]
        assert state["hash"] == f"#{expected}"

    for expected in reversed(top_ids[:3]):
        body.send_keys("p")
        assert driver.execute_script(_MARKER_PROBE)["id"] == expected

    # p at the first top episode stays put rather than wrapping or clearing.
    body.send_keys("p")
    assert driver.execute_script(_MARKER_PROBE)["id"] == top_ids[0]

    # ...and n at the last one does the same.
    driver.find_element(By.ID, top_ids[-1]).click()
    body.send_keys("n")
    assert driver.execute_script(_MARKER_PROBE)["id"] == top_ids[-1]


def test_escape_clears_the_marker_and_the_hash(app_server, browser):
    driver, _wait = open_show(browser, app_server)
    body = driver.find_element(By.TAG_NAME, "body")
    driver.find_element(By.ID, driver.execute_script(_TOP_ROW_IDS)[2]).click()
    assert driver.execute_script(_MARKER_PROBE)["marked"] == 1

    body.send_keys(Keys.ESCAPE)
    cleared = driver.execute_script(_MARKER_PROBE)
    assert cleared["marked"] == 0 and cleared["hash"] == ""
    # Clearing the hash must not throw the reader off the show.
    assert SHOW in driver.current_url


@pytest.mark.parametrize("key", ["n", "p", "h"])
def test_shortcuts_do_not_fire_while_typing_in_the_search_box(app_server, browser, key):
    "Show names have n, p and h in them."
    driver, _wait = open_show(browser, app_server)
    box = driver.find_element(By.NAME, "imdb_show_id")
    box.clear()
    box.send_keys(key)

    state = driver.execute_script(_MARKER_PROBE)
    assert state["marked"] == 0
    assert not driver.execute_script(_TOGGLE_PROBE)["hiding"]
    assert box.get_attribute("value") == key


# ---------------------------------------------------------------------------
# Percentage slider, number box and presets
# ---------------------------------------------------------------------------


def test_slider_and_number_box_stay_in_sync(app_server, browser):
    driver, _wait = open_show(browser, app_server)
    require_jquery(driver)

    # Both start on the percentage the page was loaded with.
    assert driver.find_element(By.ID, "max_rank_pct_slider").get_attribute("value") == "20"
    assert driver.find_element(By.ID, "max_rank_pct").get_attribute("value") == "20"

    # Typing in the number box moves the slider, without navigating.
    number = driver.find_element(By.ID, "max_rank_pct")
    number.clear()
    number.send_keys("35")
    assert driver.find_element(By.ID, "max_rank_pct_slider").get_attribute("value") == "35"
    assert "/20" in driver.current_url

    # Dragging the slider mirrors into the number box, then navigates on release.
    driver.execute_script("""
        const slider = document.getElementById('max_rank_pct_slider');
        slider.value = 60;
        slider.dispatchEvent(new Event('input'));
        """)
    assert driver.find_element(By.ID, "max_rank_pct").get_attribute("value") == "60"


def test_preset_buttons_reload_the_show_at_that_percentage(app_server, browser):
    driver, wait = open_show(browser, app_server)
    require_jquery(driver)

    before = driver.execute_script(_TOGGLE_PROBE)["below"]
    driver.find_element(By.CSS_SELECTOR, '.pct-preset[data-value="50"]').click()
    wait.until(lambda d: d.current_url.endswith(f"/episodes/{SHOW}/50"))
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))

    after = driver.execute_script(_TOGGLE_PROBE)
    # A wider cutoff means fewer episodes below it.
    assert after["below"] < before
    assert driver.find_element(By.ID, "max_rank_pct").get_attribute("value") == "50"


def test_changing_the_percentage_keeps_your_place(app_server, browser):
    "The hash rides along, so tidying the cutoff does not lose the marker."
    driver, wait = open_show(browser, app_server)
    require_jquery(driver)
    row_id = driver.execute_script(_TOP_ROW_IDS)[4]
    driver.find_element(By.ID, row_id).click()

    driver.find_element(By.CSS_SELECTOR, '.pct-preset[data-value="80"]').click()
    wait.until(lambda d: "/80" in d.current_url)
    wait.until(EC.presence_of_element_located((By.ID, "episodes-table")))

    restored = driver.execute_script(_MARKER_PROBE)
    assert restored["hash"] == f"#{row_id}" and restored["id"] == row_id


# ---------------------------------------------------------------------------
# Row colouring
# ---------------------------------------------------------------------------

_WASH_PROBE = """
    const rows = Array.from(document.querySelectorAll(
        '#episodes-table tbody tr[data-percentile]'));
    function rgb(row) {
        const m = getComputedStyle(row).backgroundColor.match(/\\d+/g).map(Number);
        return {r: m[0], g: m[1], b: m[2],
                pct: Number(row.dataset.percentile),
                below: row.classList.contains('below-cutoff')};
    }
    return rows.map(rgb);
"""


def test_rows_are_washed_red_below_the_cutoff_and_green_above(app_server, browser):
    "The wash, the green bars and the hide toggle all key off the same test."
    driver, _wait = open_show(browser, app_server)
    washes = driver.execute_script(_WASH_PROBE)
    threshold = 100 - 20

    assert any(w["below"] for w in washes) and any(not w["below"] for w in washes)
    for wash in washes:
        assert wash["below"] == (wash["pct"] < threshold), wash
        if wash["below"]:
            assert wash["r"] > wash["g"], f"below-cutoff row should read red: {wash}"
        else:
            assert wash["g"] >= wash["r"], f"top row should read green: {wash}"

    # The best episode is the greenest and the worst is the reddest.
    best = max(washes, key=lambda w: w["pct"])
    worst = min(washes, key=lambda w: w["pct"])
    assert best["r"] < worst["r"] and best["g"] > best["r"]


_SEASON_WASH_PROBE = """
    return Array.from(document.querySelectorAll(
        '#seasons-table tbody tr[data-percentile]')).map(function(row) {
        const m = getComputedStyle(row).backgroundColor.match(/\\d+/g).map(Number);
        return {r: m[0], g: m[1], b: m[2], pct: Number(row.dataset.percentile)};
    });
"""


def test_seasons_are_washed_against_an_average_season(app_server, browser):
    "Same ramp as the episodes table, pivoted on 50 rather than on the cutoff."
    driver, _wait = open_show(browser, app_server)
    washes = driver.execute_script(_SEASON_WASH_PROBE)

    assert len(washes) == 4
    for wash in washes:
        if wash["pct"] < 50:
            assert wash["r"] > wash["g"], f"a below-average season should read red: {wash}"
        else:
            assert wash["g"] >= wash["r"], f"an above-average season should read green: {wash}"

    # Ordered by percentile, the wash runs monotonically from red to green.
    ramp = sorted(washes, key=lambda w: w["pct"])
    assert ramp[0]["r"] >= ramp[-1]["r"] and ramp[0]["g"] <= ramp[-1]["g"]

    # The cutoff slider retunes the episodes table; a season is not measured
    # against the cutoff, so its wash must not move with it.
    driver.get(f"{app_server}/episodes/{SHOW}/80")
    WebDriverWait(driver, timeout=20).until(EC.presence_of_element_located((By.ID, "seasons-table")))
    assert driver.execute_script(_SEASON_WASH_PROBE) == washes

    # Redux's two seasons sit further than the 25-point span from the pivot, so
    # they clamp to the ends of the ramp — which is what stops season averages,
    # which cluster hard around 50, from all washing the same pale yellow.
    driver.get(f"{app_server}/episodes/{fixture_data.REDUX_SHOW_TCONST}")
    WebDriverWait(driver, timeout=20).until(EC.presence_of_element_located((By.ID, "seasons-table")))
    redux = driver.execute_script(_SEASON_WASH_PROBE)
    assert [w["pct"] for w in redux] == [22, 77]
    assert (redux[0]["r"], redux[0]["g"], redux[0]["b"]) == (255, 190, 190)
    assert (redux[1]["r"], redux[1]["g"], redux[1]["b"]) == (190, 245, 190)


def test_percentile_bars_match_the_percentiles(app_server, browser):
    "Server-rendered widths, so the bar cannot disagree with the number."
    driver, _wait = open_show(browser, app_server)
    bars = driver.execute_script("""
        return Array.from(document.querySelectorAll(
            '#episodes-table tbody tr[data-percentile]')).map(function(row) {
            const fill = row.querySelector('.pct-fill');
            const track = row.querySelector('.pct-track');
            return {
                pct: Number(row.dataset.percentile),
                width: fill.getBoundingClientRect().width,
                track: track.getBoundingClientRect().width,
                isTop: fill.classList.contains('is-top'),
                cutoff: row.querySelector('.pct-cutoff').style.left,
            };
        });
        """)
    assert bars
    for bar in bars:
        assert bar["cutoff"] == "80%"
        assert bar["isTop"] == (bar["pct"] >= 80)
        expected = bar["track"] * bar["pct"] / 100
        # min-width keeps a percentile of 0 visible, hence the floor.
        assert abs(bar["width"] - max(expected, 2)) < 2, bar


def test_episode_page_has_no_javascript_errors(app_server, browser):
    "A thrown error would leave the marker, the toggle and the header dead."
    driver, _wait = open_show(browser, app_server)
    driver.find_element(By.TAG_NAME, "body").send_keys("n")
    try:
        entries = driver.get_log("browser")
    except WebDriverException:
        pytest.skip("this browser does not expose a console log")
    severe = [
        entry
        for entry in entries
        if entry["level"] == "SEVERE"
        # Bootstrap's cdn images and the buymeacoffee badge are not the app.
        and not re.search(r"favicon|buymeacoffee|net::ERR", entry["message"])
    ]
    assert severe == []
