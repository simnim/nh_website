# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Everything runs through [uv](https://docs.astral.sh/uv/) (Python 3.14).

```bash
./scripts/dev.sh                      # hot-reloading uvicorn on 127.0.0.1:5555 (HOST/PORT env vars override)
uv run pytest                         # whole suite
uv run pytest -m "not browser"        # fast suite: everything but selenium, in seconds
uv run pytest -m "not realdata"       # skip tests that need ~/.nh-website-data loaded
uv run pytest tests/test_routes.py::test_name   # single test
uv run pre-commit run --all-files     # ruff (lint + import sort), black, sqlfluff (sqlite dialect)
```

`pyproject.toml` sets `asyncio_mode = "auto"`, so async test functions need no decorator.

## Architecture

A FastAPI + Jinja2 site (`app/main.py`, ~330 lines — the whole server) that renders four things
from three read-only SQLite databases. It never writes to them; they are produced elsewhere.

**Data ownership is the thing to understand first.**

| DB | Path key | Written by |
| --- | --- | --- |
| `imdb.db` | `tv` | `cron/refresh_imdb_data.sh` weekly (downloads imdb tsvs → `cron/imdb_load.py` → `app/sql/episodes/create-tables.sql` + `add-indexes.sql`) |
| `top_cat.db` | `cat` | the separate [top-cat](https://github.com/simnim/top-cat) repo's scraper |
| `top-books.db` | `books` | that same scraper host |

They live in `~/.nh-website-data` by default; `NH_WEBSITE_DATA_DIR` overrides the directory.
Because the imdb refresh rebuilds a temp db and `mv`s it into place, an open aiosqlite
connection would keep pointing at the old unlinked inode — hence `watch_and_reload_dbs()`, which
polls mtimes every 60s, swaps the connection, and closes the old one after a 30s grace period.

**Queries live in SQL files, not Python.** `aiosql.from_path(app/sql, "aiosqlite", kwargs_only=True)`
builds `QS`, where the subdirectory becomes the namespace and the `-- name:` header becomes the
method: `app/sql/episodes/get-basic-show-info.sql` → `QS.episodes.get_basic_show_info(db["tv"], ...)`.
Trailing sigils matter — `^` returns one row, `#` runs a script, bare returns an async row iterator.
Add a query by adding a file; no Python registration.

**Top Episodes is where the complexity is.** `ratings.percentile` and `is_top_episode` are computed
in SQL (`add-indexes.sql` for the column, `get-top-episodes-for-show.sql` for the flag against
`max_rank_pct`), and every episode is sent to the browser. `app/templates/episodes.html` (500 lines,
inline JS, jquery-ui autocomplete from a CDN) does the rest client-side: row colouring, the percentile
bar, next/prev top-episode keyboard nav with url hashes, the hide-below-cutoff toggle, and the sticky
header. Show search is fts5 over `show_names_fts`; `clean_txt()` strips specials and builds a
`term* AND term*` prefix query, and `POST /episodes` resolves a typed-but-unselected show name by
running that same search and taking the first hit.

Unknown or malformed show ids fall through to `_episodes_landing(..., not_found=...)`, a 404 that
still renders the search page — old links go stale because the weekly rebuild drops titles.

## Tests

`tests/conftest.py` documents three ways to drive the app, cheapest first:

* `client` — in-process `TestClient` over synthetic databases. Default for routes, queries, templates.
* `browser` + `app_server` — headless selenium against a real uvicorn on an OS-assigned port
  (`@pytest.mark.browser`). Skips when no chromedriver/geckodriver is on PATH — Selenium Manager
  cannot provision drivers on linux/aarch64, which is this site's usual home (a Raspberry Pi).
* `cat_conn` / `tv_conn` / `books_conn` — the real databases (`@pytest.mark.realdata`), skipped when
  not populated. Only for asserting things about the real data itself.

`tests/fixture_data.py` builds the synthetic databases once per session. For imdb it uses the app's
own DDL, so `create-tables.sql` and `add-indexes.sql` get exercised; for the two scraper databases
the `CREATE` statements there are this suite's copy of a contract owned by the top-cat repo, and
must be updated alongside it. Ratings are a fixed permutation, so percentiles and top/not-top
splits are identical on every run.

The `client` fixture monkeypatches `main.DB_PATHS` rather than the env var, because `DB_PATHS` is
built at import time and `app.main` is already imported by then.

## Notes

* `README.md` and `top_episodes.md` still refer to `flask_nh_site.py`; the site was ported to
  FastAPI and that file no longer exists.
* `k8s/` is unused (see `k8s/README.md`). The `Dockerfile` runs as `appuser`, whose home must match
  the data volume mount since paths go through `os.path.expanduser`.
