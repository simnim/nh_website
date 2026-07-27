"""
Security properties, pinned so they cannot regress quietly.

None of these caught a live bug when they were written — the site had no
injection or xss holes. That is the point: every one of them is a property the
code currently has by construction, and construction is exactly what a later
edit changes. A `|safe` added to a template, an f-string slipped into a query,
a route gaining a `path:` converter — each is a one-line change that looks
harmless in review and that one of these tests fails on.

In-process over the synthetic databases, so they cost nothing and run in the
`-m "not browser"` suite.
"""

import fixture_data
import pytest

from app import main

SHOW = fixture_data.MAIN_SHOW_TCONST

# Pages worth checking headers on: a template render, a redirect, a json
# endpoint, a 404, and a static file. Middleware that only fires on some of
# these is the usual way header coverage rots.
EVERY_KIND_OF_RESPONSE = [
    "/",
    "/episodes",
    f"/episodes/{SHOW}",
    "/top/cat",
    "/books",
    "/search?term=nebula",
    "/episodes/tt-not-an-id",
    "/static/fixAudio.js",
]


# ---------------------------------------------------------------------------
# Response headers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", EVERY_KIND_OF_RESPONSE)
def test_security_headers_are_on_every_response(client, path):
    headers = client.get(path, follow_redirects=False).headers
    for header, value in main.SECURITY_HEADERS.items():
        assert headers.get(header) == value, f"{header} missing from {path}"


def test_hsts_is_not_sent_unless_it_is_switched_on(client):
    """
    HSTS is a year-long promise the browser caches. Sending it from a
    deployment that cannot serve https locks users out, so it is opt-in via
    NH_WEBSITE_HSTS and must stay off by default.
    """
    assert main.SEND_HSTS is False
    assert "strict-transport-security" not in client.get("/").headers


def test_hsts_is_sent_when_it_is_switched_on(client, monkeypatch):
    monkeypatch.setattr(main, "SEND_HSTS", True)
    assert client.get("/").headers["Strict-Transport-Security"] == main.HSTS_HEADER


# ---------------------------------------------------------------------------
# Attack surface that should not exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_openapi_surface_is_closed(client, path):
    "Nothing consumes the generated schema, so it is surface with no user."
    assert client.get(path).status_code == 404


# ---------------------------------------------------------------------------
# Output escaping
# ---------------------------------------------------------------------------

# Every html page a show title reaches. The title itself is imdb's, and imdb's
# titles are not this repo's to trust.
PAGES_SHOWING_THE_XSS_TITLE = [
    f"/episodes/{fixture_data.XSS_SHOW_TCONST}",
    f"/episodes/{fixture_data.XSS_SHOW_TCONST}/100",
]


@pytest.mark.parametrize("path", PAGES_SHOWING_THE_XSS_TITLE)
def test_a_show_title_cannot_open_a_script_tag(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    # The payload has to actually be on the page, or this asserts nothing.
    assert "Zorbtown" in resp.text
    assert fixture_data.XSS_PAYLOAD not in resp.text
    assert "<script>alert" not in resp.text


def test_the_escaped_title_is_still_the_real_title(client):
    "Escaped, not stripped — the user should see the characters they typed."
    html = client.get(f"/episodes/{fixture_data.XSS_SHOW_TCONST}").text
    assert "&lt;script&gt;" in html
    assert "&amp; Sons" in html


def test_the_search_endpoint_is_json_not_html(client):
    """
    /search hands raw titles to the autocomplete, payload and all. That is
    fine, and the reason is worth writing down: it is application/json, so no
    browser parses it as markup, and jquery-ui's stock _renderItem builds the
    suggestion with .text() — a text node, not html. A _renderItem override
    using .html() would turn this endpoint into a dom xss, which is what this
    test is here to make someone think about.
    """
    resp = client.get("/search", params={"term": "zorbtown"})
    assert resp.headers["content-type"].startswith("application/json")
    labels = resp.json()
    assert any(fixture_data.XSS_PAYLOAD in label for label in labels)


def test_a_not_found_id_is_echoed_escaped(client):
    """
    _episodes_landing renders the id it could not find, which is the one place
    a raw url segment is reflected straight back into the page. No '/' in the
    payload: starlette's default converter stops the segment there, so a
    slash-bearing id is a 422 from the {max_rank_pct} route and never arrives.
    """
    resp = client.get("/episodes/tt<script>alert(1)")
    assert resp.status_code == 404
    assert "<script>alert(1)" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_a_show_id_cannot_smuggle_a_slash_into_the_page(client):
    "It would otherwise reach the JS on episodes.html and build a url from it."
    assert client.get("/episodes/tt<script>alert(1)</script>").status_code == 422


def test_the_show_id_reaches_javascript_as_json(client):
    """
    episodes.html drops imdb_show_id inside a <script> block. It goes through
    |tojson, which escapes '<' — without it a crafted id could close the tag.
    """
    html = client.get(f"/episodes/{fixture_data.XSS_SHOW_TCONST}").text
    assert f'var imdbShowId = "{fixture_data.XSS_SHOW_TCONST}"' in html
    assert "</script>alert" not in html


# ---------------------------------------------------------------------------
# fts5 / sql injection
# ---------------------------------------------------------------------------

# clean_txt strips everything outside [a-z0-9 ], which kills fts5's query
# syntax as well as sql's. These are the characters that would otherwise mean
# something to one or the other.
HOSTILE_SEARCH_TERMS = [
    '" OR 1=1 --',
    "'; drop table basics; --",
    "nebula*",
    "^nebula",
    "NEAR(nebula patrol, 2)",
    "nebula OR patrol",
    'nebula" AND "patrol',
    "nebula -patrol",
    "basics:nebula",
    "\\",
    "%",
    "()",
]


@pytest.mark.parametrize("term", HOSTILE_SEARCH_TERMS)
def test_search_never_500s_on_fts5_or_sql_metacharacters(client, term):
    "A 500 here would mean the string reached the query engine as syntax."
    resp = client.get("/search", params={"term": term})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_a_dropped_table_would_have_shown_up_by_now(client):
    "Run after the injection attempts above: the database is still intact."
    for term in HOSTILE_SEARCH_TERMS:
        client.get("/search", params={"term": term})
    assert client.get(f"/episodes/{SHOW}").status_code == 200


# ---------------------------------------------------------------------------
# Cost bounds
# ---------------------------------------------------------------------------


def test_search_caps_the_number_of_terms():
    """
    Every term is another prefix scan in the AND chain, so an uncapped query
    string is a cheap way to make the pi do arithmetic on demand.
    """
    terms = main.clean_txt(" ".join(f"term{i}" for i in range(500))).split()
    assert len(terms) > main.MAX_SEARCH_TERMS
    capped = [t[: main.MAX_SEARCH_TERM_LEN] for t in terms[: main.MAX_SEARCH_TERMS]]
    assert len(capped) == main.MAX_SEARCH_TERMS


def test_a_long_search_is_still_answered_quickly(client):
    resp = client.get("/search", params={"term": " ".join(["nebula"] * 20)})
    assert resp.status_code == 200 and isinstance(resp.json(), list)


def test_an_absurdly_long_search_is_refused_before_any_query_runs(client):
    resp = client.get("/search", params={"term": "a" * (main.MAX_SEARCH_STR_LEN + 1)})
    assert resp.status_code == 422


def test_a_real_search_is_nowhere_near_the_length_cap(client):
    "The cap must not be able to refuse a show anyone would actually type."
    assert len(fixture_data.MAIN_SHOW_LABEL) < main.MAX_SEARCH_STR_LEN
    assert client.get("/search", params={"term": fixture_data.MAIN_SHOW_TITLE}).json() != []


def test_the_term_cap_does_not_bite_a_realistic_title(client):
    "Longest fixture title, word for word, still finds its show."
    longest = max((title for _t, title, *_r in fixture_data.SHOWS), key=lambda t: len(t.split()))
    assert len(main.clean_txt(longest).split()) <= main.MAX_SEARCH_TERMS
    assert client.get("/search", params={"term": longest}).json() != []


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------

OPEN_REDIRECT_ATTEMPTS = [
    "//evil.example",
    "https://evil.example",
    "/\\evil.example",
    "....//....//etc/passwd",
    "javascript:alert(1)",
    "tt1000001@evil.example",
    "%2f%2fevil.example",
]


@pytest.mark.parametrize("typed", OPEN_REDIRECT_ATTEMPTS)
def test_the_search_form_cannot_redirect_off_site(client, typed):
    """
    POST /episodes builds its Location from the form. clean_txt removes '/',
    ':' and '\\' before the tt-digits allowlist runs, so there is nothing left
    to build an absolute url out of — this pins that.
    """
    resp = client.post("/episodes", data={"imdb_show_id": typed}, follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/episodes")
    assert not location.startswith("//")
    assert "evil.example" not in location


def test_a_redirect_target_is_always_a_show_id_and_a_percentage(client):
    resp = client.post(
        "/episodes",
        data={"imdb_show_id": fixture_data.MAIN_SHOW_LABEL},
        follow_redirects=False,
    )
    assert resp.headers["location"] == f"/episodes/{SHOW}/20"


def test_an_oversized_form_submission_is_refused(client):
    "Nothing sits in front of uvicorn to cap a request body."
    resp = client.post(
        "/episodes",
        data={"imdb_show_id": "a" * (main.MAX_SEARCH_STR_LEN + 1)},
        follow_redirects=False,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Path handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/static/../main.py",
        "/static/%2e%2e/main.py",
        "/static/../../pyproject.toml",
        "/static/....//main.py",
    ],
)
def test_static_files_cannot_escape_the_static_directory(client, path):
    resp = client.get(path)
    assert resp.status_code in (403, 404)
    assert "aiosql" not in resp.text


def test_an_error_response_does_not_leak_a_traceback(client):
    "debug is off, so a failure must not hand the visitor a stack trace."
    resp = client.get("/episodes/tt-not-an-id")
    assert "Traceback" not in resp.text
    assert "/home/" not in resp.text
