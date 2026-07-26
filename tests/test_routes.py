"""
Every route, against the synthetic databases.

These run in-process over a TestClient, so they cover the parts of the site
whose real data only exists on the scraper machine (/top, /permalink, /books)
and they cannot be knocked over by this week's imdb dump.
"""

import re

import fixture_data
import pytest
from conftest import MOBILE_UA

SHOW = fixture_data.MAIN_SHOW_TCONST
SHOW_TITLE = fixture_data.MAIN_SHOW_TITLE

EPISODE_ROW_RE = re.compile(r'<tr id="([^"]+)" data-percentile="(\d+)">')
CUTOFF_RE = re.compile(r'class="pct-cutoff" style="left: (-?\d+)%"')
FILL_RE = re.compile(r'class="pct-fill( is-top)?"\s*\n?\s*style="width: (\d+)%"')


def episode_rows(html):
    "[(row id, percentile)] in document order."
    return [(rid, int(pct)) for rid, pct in EPISODE_ROW_RE.findall(html)]


def visible_html(html):
    "The markup minus commented-out columns, which are not rendered to anyone."
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def episodes_table(html):
    "Just the episodes table — the page-wide <style> block mentions every class."
    start = html.index('<table id="episodes-table"')
    return visible_html(html[start : html.index("</table>", start)])


def db_episodes(fixture_tv_queries, show_id, max_rank_pct):
    queries, conn = fixture_tv_queries
    return list(queries.episodes.get_top_episodes_for_show(conn, imdb_show_id=show_id, max_rank_pct=max_rank_pct))


# ---------------------------------------------------------------------------
# Index, navigation, static files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/index"])
def test_index_serves_the_same_page_on_both_paths(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "<title>Nick's Website</title>" in resp.text
    # The page's reason for existing: pointing at the projects.
    assert "https://github.com/simnim/top-cat" in resp.text
    for link in ("/top/cat", "/top/dog", "/episodes"):
        assert f'href="{link}"' in resp.text


def test_nav_is_on_every_page(client):
    for path in ["/", "/episodes", f"/episodes/{SHOW}", "/top/cat", "/books"]:
        html = client.get(path).text
        assert 'href="/top/cat"' in html and 'href="/episodes"' in html, path
        assert "buymeacoffee.com/simnim" in html, path


def test_mobile_user_agent_gets_the_compact_nav(client):
    desktop = client.get("/").text
    mobile = client.get("/", headers={"user-agent": MOBILE_UA}).text
    assert "Nick Hahner</a>" in desktop and "🐱 Top Cat" in desktop
    # Phone-width navbar: initials and bare emoji instead of full labels.
    assert ">NH</a>" in mobile and "🐱 Top Cat" not in mobile
    assert 'href="/top/cat"' in mobile


@pytest.mark.parametrize(
    "user_agent, is_mobile",
    [
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", False),
        ("Mozilla/5.0 (Linux; Android 14; Pixel 8)", True),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", True),
        ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", True),
        ("Some Mobile Crawler/1.0", True),
        ("", False),
    ],
)
def test_mobile_detection(client, user_agent, is_mobile):
    html = client.get("/", headers={"user-agent": user_agent}).text
    assert (">NH</a>" in html) is is_mobile


def test_favicon_redirects_to_the_static_file(client):
    redirect = client.get("/favicon.ico", follow_redirects=False)
    assert redirect.status_code in (302, 307)
    assert redirect.headers["location"] == "/static/favicon.ico"
    followed = client.get("/favicon.ico")
    assert followed.status_code == 200
    assert followed.headers["content-type"].startswith("image/")


@pytest.mark.parametrize("path", ["/static/favicon.ico", "/static/topcat_index.jpg", "/static/fixAudio.js"])
def test_static_files_are_served(client, path):
    resp = client.get(path)
    assert resp.status_code == 200 and resp.content


# ---------------------------------------------------------------------------
# /top/{label}
# ---------------------------------------------------------------------------


def test_top_label_shows_the_ten_most_recent(client):
    html = client.get("/top/cat").text
    # The query is limit 10 and the fixture has more cats than that.
    assert html.count("> Permalink") == 10
    assert "Cat discovers stairs" in html
    # Recent first, and nothing that never made a top list.
    assert html.index("Cat discovers stairs") < html.index("A very round cat")
    assert "Never made the cut" not in html


def test_top_label_keeps_the_labels_apart(client):
    cats = client.get("/top/cat").text
    dogs = client.get("/top/dog").text
    assert "Dog greets mailman" in dogs and "Dog greets mailman" not in cats
    assert "A very round cat" in cats and "A very round cat" not in dogs
    assert "<title>Top dog</title>" in dogs


def test_top_label_renders_videos_and_images_differently(client):
    html = client.get("/top/cat").text
    # Video posts need a <video> so the audio fix-up script has something to
    # hook; everything else is an <img>, including the extensionless gallery.
    assert '<source src="https://v.redd.it/cat02/DASH_720.mp4"' in html
    assert '<img src="https://i.redd.it/cat01.jpg"' in html
    assert '<img src="https://www.reddit.com/gallery/cat03"' in html
    assert 'src="/static/fixAudio.js"' in html


def test_top_label_links_to_permalinks(client):
    html = client.get("/top/cat").text
    assert f'href="/permalink/{fixture_data.REPOSTED_HASH}/' in html


def test_top_unknown_label_is_an_empty_page(client):
    resp = client.get("/top/hamster")
    assert resp.status_code == 200
    assert "> Permalink" not in resp.text


# ---------------------------------------------------------------------------
# /permalink
# ---------------------------------------------------------------------------


def test_permalink_shows_every_posting_of_that_media(client):
    html = client.get(f"/permalink/{fixture_data.REPOSTED_HASH}").text
    assert "Cat in a box" in html and "Cat in a box (repost)" in html
    # group_concat of the labels it was ever top under.
    assert "top-cat @" in html


def test_permalink_with_a_timestamp_narrows_to_one_posting(client):
    html = client.get(f"/permalink/{fixture_data.REPOSTED_HASH}/{fixture_data.REPOSTED_TS}").text
    assert "Cat in a box (repost)" in html
    assert html.count("<h3>") == 1


def test_permalink_for_unknown_media_still_renders(client):
    resp = client.get("/permalink/nosuchhash")
    assert resp.status_code == 200 and "<html" in resp.text.lower()


# ---------------------------------------------------------------------------
# /books
# ---------------------------------------------------------------------------


def test_books_defaults_to_the_books_category(client):
    resp = client.get("/books")
    assert resp.status_code == 200
    assert "<title>Top Books</title>" in resp.text
    assert "Fixture Tale" in resp.text
    assert "Deep Sea Fixtures" not in resp.text
    # Every category is offered in the dropdown regardless of which is shown.
    for category in ("Books", "Science"):
        assert f'href="/books/{category}"' in resp.text


def test_books_category_filters(client):
    html = client.get("/books/Science").text
    assert "Deep Sea Fixtures" in html and "Fixture Tale" not in html


def test_books_unknown_category_is_empty(client):
    resp = client.get("/books/Nonexistent")
    assert resp.status_code == 200 and "Fixture Tale" not in resp.text


# ---------------------------------------------------------------------------
# /episodes — landing page
# ---------------------------------------------------------------------------


def test_episodes_landing_offers_search_and_recommendations(client):
    resp = client.get("/episodes")
    assert resp.status_code == 200
    assert "Show Name Search" in resp.text
    assert 'id="episodes-table"' not in resp.text
    assert 'href="/episodes/tt0112178/30"' in resp.text  # the sci-fi list
    assert "Pareto" in resp.text or "pareto" in resp.text


@pytest.mark.parametrize("path", ["/episodes/tt9999999", "/episodes/tt-not-an-id"])
def test_episodes_unknown_or_malformed_show_is_a_404_page_not_a_500(client, path):
    """
    Both used to raise: one on int() and one on subscripting a missing row.

    Stale links are normal — the weekly rebuild drops titles — so this lands on
    the landing page with a note rather than an error page.
    """
    resp = client.get(path)
    assert resp.status_code == 404
    assert 'id="show-not-found"' in resp.text
    assert "Show Name Search" in resp.text
    assert 'id="episodes-table"' not in resp.text


# ---------------------------------------------------------------------------
# /episodes — a show
# ---------------------------------------------------------------------------


def test_episodes_page_shows_the_metadata(client):
    resp = client.get(f"/episodes/{SHOW}")
    assert resp.status_code == 200
    assert f"<title>{SHOW_TITLE} 📺 {SHOW}</title>" in resp.text
    for value in (SHOW_TITLE, "1995", "2001", "45 min", "Action,Adventure,Sci-Fi"):
        assert value in resp.text
    # The search box comes back filled in with what you searched for.
    assert f'value="{fixture_data.MAIN_SHOW_LABEL}"' in resp.text


def test_episodes_page_lists_every_episode_with_its_percentile(client, fixture_tv_queries):
    html = client.get(f"/episodes/{SHOW}").text
    rows = episode_rows(html)
    expected = db_episodes(fixture_tv_queries, fixture_data.MAIN_SHOW_ID, 20)

    assert len(rows) == fixture_data.MAIN_SHOW_EPISODES == len(expected)
    assert [pct for _id, pct in rows] == [int(ep["percentile"]) for ep in expected]
    # Canonical order, and row ids addressable as url hashes.
    assert rows[0][0] == "s1e1" and rows[-1][0] == "s4e25"


def test_episode_colouring_matches_the_sql_top_flag(client, fixture_tv_queries):
    "The green bars, the red/green wash and n/p navigation all key off this."
    html = client.get(f"/episodes/{SHOW}/20").text
    expected_top = sum(ep["is_top_episode"] for ep in db_episodes(fixture_tv_queries, fixture_data.MAIN_SHOW_ID, 20))

    assert expected_top > 0
    assert html.count("pct-fill is-top") == expected_top
    assert html.count("— top episode") == expected_top


@pytest.mark.parametrize("pct", [5, 20, 50, 100])
def test_cutoff_marker_tracks_the_requested_percentage(client, pct):
    html = client.get(f"/episodes/{SHOW}/{pct}").text
    assert f'data-threshold="{100 - pct}"' in html
    assert f"cutoff = top {pct}%" in html
    assert set(CUTOFF_RE.findall(html)) == {str(100 - pct)}


@pytest.mark.parametrize("given, applied", [(0, 1), (500, 100), (-3, 1)])
def test_out_of_range_percentages_are_clamped(client, given, applied):
    "A url like /episodes/tt.../500 drew its cutoff marker 400% off the track."
    resp = client.get(f"/episodes/{SHOW}/{given}")
    assert resp.status_code == 200
    assert f'data-threshold="{100 - applied}"' in resp.text
    assert all(0 <= int(left) <= 100 for left in CUTOFF_RE.findall(resp.text))


def test_show_id_works_with_or_without_the_tt_prefix(client):
    with_tt = client.get(f"/episodes/{SHOW}").text
    without = client.get(f"/episodes/{fixture_data.MAIN_SHOW_ID}").text
    assert episode_rows(with_tt) == episode_rows(without)


def test_episodes_without_season_numbers_still_get_a_row_id(client):
    "imdb lists unaired specials with no season or episode number."
    html = client.get(f"/episodes/{fixture_data.NULL_NUMBERED_SHOW_TCONST}").text
    ids = [rid for rid, _pct in episode_rows(html)]
    assert "s1e1" in ids
    # Falls back to the loop index so the row is still a hash target.
    assert any(rid.startswith("row") for rid in ids)


def test_seasons_summary_is_rendered(client, fixture_tv_queries):
    queries, conn = fixture_tv_queries
    seasons = list(queries.episodes.get_seasons_summary(conn, imdb_show_id=fixture_data.MAIN_SHOW_ID))
    html = client.get(f"/episodes/{SHOW}").text
    body = html[html.index('id="seasons"') : html.index('id="episodes"')]

    assert len(seasons) == 4
    for season in seasons:
        assert f"> {season['seasonNumber']} </td>" in body
        assert f'style="width: {season["average_percentile"]}%"' in body
    # A season has no top/not-top verdict, so its bar carries no cutoff tick.
    assert "pct-cutoff" not in body


def test_mobile_episode_table_drops_the_wide_columns(client):
    desktop = episodes_table(client.get(f"/episodes/{SHOW}").text)
    mobile = episodes_table(client.get(f"/episodes/{SHOW}", headers={"user-agent": MOBILE_UA}).text)

    assert "Num Votes" in desktop and "Num Votes" not in mobile
    assert "pct-track" in desktop and "pct-track" not in mobile
    # Same rows either way — only the columns change.
    assert episode_rows(mobile) == episode_rows(desktop)
    assert mobile.count("<th") < desktop.count("<th")


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


def test_search_returns_autocomplete_labels(client):
    results = client.get("/search", params={"term": "nebula patrol"}).json()
    assert fixture_data.MAIN_SHOW_LABEL in results
    # Sorted by total votes, so the show people actually watch comes first.
    assert results[0] == fixture_data.MAIN_SHOW_LABEL


def test_search_matches_on_word_prefixes(client):
    "Every word gets a trailing *, which is what makes it type-ahead."
    assert client.get("/search", params={"term": "nebu pat"}).json() == (
        client.get("/search", params={"term": "nebula patrol"}).json()
    )


def test_search_ignores_punctuation(client):
    assert (
        client.get("/search", params={"term": "quiet: bakery!"}).json()
        == client.get("/search", params={"term": "quiet bakery"}).json()
        != []
    )


@pytest.mark.parametrize("term", ["", "   ", "!!!", "%^&*"])
def test_search_with_nothing_to_search_for_returns_nothing(client, term):
    "Used to be a 500: an fts5 match string of '*' is a syntax error."
    resp = client.get("/search", params={"term": term})
    assert resp.status_code == 200 and resp.json() == []


def test_search_without_a_term_at_all_returns_nothing(client):
    resp = client.get("/search")
    assert resp.status_code == 200 and resp.json() == []


def test_search_with_no_matches_returns_nothing(client):
    assert client.get("/search", params={"term": "zzzznothing"}).json() == []


# ---------------------------------------------------------------------------
# POST /episodes — the search form
# ---------------------------------------------------------------------------


def post_episodes(client, path="/episodes", **form):
    return client.post(path, data=form, follow_redirects=False)


def test_form_submit_with_an_autocomplete_pick_redirects_to_the_show(client):
    resp = post_episodes(client, imdb_show_id=fixture_data.MAIN_SHOW_LABEL)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/episodes/{SHOW}/20"


def test_form_submit_keeps_the_chosen_percentage(client):
    resp = post_episodes(client, imdb_show_id=fixture_data.MAIN_SHOW_LABEL, max_rank_pct=50)
    assert resp.headers["location"] == f"/episodes/{SHOW}/50"


def test_form_submit_clamps_a_silly_percentage(client):
    resp = post_episodes(client, imdb_show_id=fixture_data.MAIN_SHOW_LABEL, max_rank_pct=500)
    assert resp.headers["location"] == f"/episodes/{SHOW}/100"


def test_form_submit_accepts_a_bare_show_id(client):
    "Pasting the digits off an imdb url, with or without the tt."
    for typed in (str(fixture_data.MAIN_SHOW_ID), SHOW):
        resp = post_episodes(client, imdb_show_id=typed)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/episodes/")
        assert client.get(resp.headers["location"]).status_code == 200


def test_form_submit_of_free_text_falls_back_to_a_search(client):
    "Hitting enter before the autocomplete answered still finds the show."
    resp = post_episodes(client, imdb_show_id="nebula")
    assert resp.headers["location"] == f"/episodes/{SHOW}/20"


def test_form_submit_of_gibberish_goes_back_to_the_landing_page(client):
    assert post_episodes(client, imdb_show_id="zzzzznope").headers["location"] == ("/episodes")


@pytest.mark.parametrize("typed", ["", "   ", "!!!", "x"])
def test_form_submit_of_nothing_useful_goes_back_to_the_landing_page(client, typed):
    "A single character is too short to search on, so it is treated as empty."
    resp = post_episodes(client, imdb_show_id=typed)
    assert resp.status_code == 303 and resp.headers["location"] == "/episodes"


def test_form_submit_is_accepted_on_every_form_of_the_url(client):
    "The form posts to '', so it lands on whichever url the page was loaded at."
    for path in ["/episodes", f"/episodes/{SHOW}", f"/episodes/{SHOW}/30"]:
        resp = post_episodes(client, path, imdb_show_id=fixture_data.MAIN_SHOW_LABEL)
        assert resp.status_code == 303, path
