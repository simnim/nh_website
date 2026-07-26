import asyncio
import contextlib
import mimetypes
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

# https://nackjicholson.github.io/aiosql/pydoc/aiosql.html
import aiosql
import aiosqlite
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

THIS_DIR = Path(__file__).parent

QS = aiosql.from_path(THIS_DIR / "sql", "aiosqlite", kwargs_only=True)

# Overridable so a test run (or a second instance) can point at its own data
# without touching the real ~/.nh-website-data.
DATA_DIR = os.environ.get("NH_WEBSITE_DATA_DIR", "~/.nh-website-data")

DB_PATHS = {
    "cat": f"{DATA_DIR}/top_cat.db",
    "tv": f"{DATA_DIR}/imdb.db",
    "books": f"{DATA_DIR}/top-books.db",
}

# The weekly cron/refresh_imdb_data.sh rebuilds imdb.db and atomically mv's it
# into place. Without this poller, the aiosqlite connection opened below would
# keep pointing at the old (unlinked) inode for the life of the process.
DB_RELOAD_POLL_SECONDS = 60
DB_CLOSE_GRACE_SECONDS = 30

db = {}
db_mtimes = {}


async def open_db(file_name):
    path = os.path.expanduser(file_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = await aiosqlite.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_mtime(file_name):
    try:
        return os.stat(os.path.expanduser(file_name)).st_mtime
    except FileNotFoundError:
        return None


async def _delayed_close(conn, delay=DB_CLOSE_GRACE_SECONDS):
    await asyncio.sleep(delay)
    with contextlib.suppress(Exception):
        await conn.close()


async def _reload_db(key, file_name):
    new_conn = await open_db(file_name)
    old_conn = db.get(key)
    db[key] = new_conn
    if old_conn is not None:
        asyncio.create_task(_delayed_close(old_conn))


async def watch_and_reload_dbs():
    while True:
        await asyncio.sleep(DB_RELOAD_POLL_SECONDS)
        for key, file_name in DB_PATHS.items():
            try:
                mtime = await asyncio.to_thread(_get_mtime, file_name)
                if mtime is not None and mtime != db_mtimes.get(key):
                    await _reload_db(key, file_name)
                    db_mtimes[key] = mtime
            except Exception as e:
                print(f"WARNING: db reload check failed for {key!r}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db["cat"], db["tv"], db["books"] = await asyncio.gather(
        *(open_db(path) for path in DB_PATHS.values())
    )
    for key, file_name in DB_PATHS.items():
        db_mtimes[key] = _get_mtime(file_name)

    watcher_task = asyncio.create_task(watch_and_reload_dbs())
    yield
    watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await watcher_task
    for conn in db.values():
        await conn.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=THIS_DIR / "static"), name="static")
templates = Jinja2Templates(directory=THIS_DIR / "templates")


class MobileMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ua = request.headers.get("user-agent", "").lower()
        request.state.is_mobile = any(
            m in ua for m in ["mobile", "android", "iphone", "ipad"]
        )
        return await call_next(request)


app.add_middleware(MobileMiddleware)


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse(url="/static/favicon.ico")


@app.get("/")
@app.get("/index")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


# Just fetch the most recent 10 top posts
@app.get("/top/{label}")
async def show_subpath(request: Request, label: str):
    title = f"Top {label}"
    # We need to know if the url is for a video or a picture!
    posts = [
        {**dict(row), "type": _media_type(row["media"])}
        async for row in QS.topcat.get_top_posts_for_flask(db["cat"], label=label)
    ]
    return templates.TemplateResponse(
        request, "top-post.html", {"title": title, "posts": posts, "label": label}
    )


def _media_type(path):
    # Reddit hands out the odd extensionless url (galleries, some crossposts);
    # guess_type says None for those, and the templates render anything that is
    # not a video as an image anyway.
    mime = mimetypes.guess_type(path or "")[0]
    return mime.split("/")[0] if mime else "image"


def clean_txt(txt):
    "Idempotent: remove special characters, lower case, minimize whitespace"
    no_specials = re.sub(r"[^a-z0-9 ]+", " ", txt.strip().lower())
    return re.sub(r"\s+", " ", no_specials).strip()


async def get_search_results_given_search_str(search_str, return_just_id=False):
    # Remove special characters and allow for prefix searches with *
    # Example 'ABC %# ^def & lol'  ->  'abc* AND def* AND lol*'
    terms = clean_txt(search_str).split()
    if not terms:
        # The autocomplete fires on every keystroke, including the one that
        # empties the box, and a bare "*" is an fts5 syntax error rather than a
        # match-everything.
        return []
    query_str = "* AND ".join(terms) + "*"
    return [
        r["value"] if return_just_id else r["label"]
        async for r in QS.episodes.search_show_names_in_full_text_index(
            db["tv"], search_str=query_str
        )
    ]


# Called by the jqueryui autocomplete widget for top-episodes
@app.get("/search")
async def search(term: str = ""):
    return await get_search_results_given_search_str(search_str=clean_txt(term))


def _clamp_pct(max_rank_pct):
    "Percentages come straight off the url, where any int is expressible."
    return min(100, max(1, max_rank_pct))


def _episodes_landing(request, max_rank_pct, not_found=None):
    "The search-and-recommendations page, with an optional 'no such show' note."
    return templates.TemplateResponse(
        request,
        "episodes.html",
        {
            "imdb_show_id": None,
            "max_rank_pct": max_rank_pct,
            "show_meta": None,
            "episodes": [],
            "seasons": [],
            "title": "📺 Top Episodes",
            "not_found": not_found,
        },
        status_code=404 if not_found else 200,
    )


@app.get("/episodes")
@app.get("/episodes/{imdb_show_id}")
@app.get("/episodes/{imdb_show_id}/{max_rank_pct}")
async def get_top_episodes_for_show(
    request: Request, imdb_show_id: str = None, max_rank_pct: int = 20
):
    max_rank_pct = _clamp_pct(max_rank_pct)
    try:
        imdb_show_id_int = int(imdb_show_id.lstrip("t")) if imdb_show_id else None
    except ValueError:
        # Hand-typed or stale url, e.g. /episodes/tt-not-an-id.
        return _episodes_landing(request, max_rank_pct, not_found=imdb_show_id)
    show_meta = await QS.episodes.get_basic_show_info(
        db["tv"], imdb_show_id=imdb_show_id_int
    )
    if imdb_show_id and show_meta is None:
        # A well-formed id for a show this database has never heard of: the
        # weekly imdb rebuild drops titles, so old links do go stale.
        return _episodes_landing(request, max_rank_pct, not_found=imdb_show_id)
    seasons = [
        row
        async for row in QS.episodes.get_seasons_summary(
            db["tv"], imdb_show_id=imdb_show_id_int
        )
    ]
    episodes = [
        row
        async for row in QS.episodes.get_top_episodes_for_show(
            db["tv"], imdb_show_id=imdb_show_id_int, max_rank_pct=max_rank_pct
        )
    ]
    title = (
        (show_meta["primaryTitle"] + " 📺 " + imdb_show_id)
        if imdb_show_id
        else "📺 Top Episodes"
    )
    return templates.TemplateResponse(
        request,
        "episodes.html",
        {
            "imdb_show_id": imdb_show_id,
            "max_rank_pct": max_rank_pct,
            "show_meta": show_meta,
            "episodes": episodes,
            "seasons": seasons,
            "title": title,
        },
    )


@app.post("/episodes")
@app.post("/episodes/{imdb_show_id}")
@app.post("/episodes/{imdb_show_id}/{max_rank_pct}")
async def post_top_episodes_for_show(
    request: Request,
    imdb_show_id: str = None,
    max_rank_pct: int = 20,
    imdb_show_id_form: str = Form("", alias="imdb_show_id"),
    max_rank_pct_form: int = Form(20, alias="max_rank_pct"),
):
    clean_imdb_id_input = clean_txt(imdb_show_id_form)
    if clean_imdb_id_input:
        # They successfully used the search popup menu: extract out the imdb id
        clean_imdb_id = (
            re.findall(r"tt[0-9]{5,8}", clean_imdb_id_input)
            or re.findall(r"^\d{5,8}$", clean_imdb_id_input)
            or [None]
        )[0]
        # OR They were extra lazy and hit enter before the search had a chance to respond.
        if clean_imdb_id is None and len(clean_imdb_id_input) >= 2:
            # Example input: "sponge" -> 0206512
            clean_imdb_id = (
                await get_search_results_given_search_str(
                    clean_imdb_id_input, return_just_id=True
                )
                or [None]
            )[0]
        # Build redirect URL
        if clean_imdb_id:
            url = f"/episodes/{clean_imdb_id}/{_clamp_pct(max_rank_pct_form or 20)}"
        else:
            url = "/episodes"
        return RedirectResponse(url=url, status_code=303)
    return RedirectResponse(url="/episodes", status_code=303)


# Just fetch the most recent 10 top posts
@app.get("/permalink/{media_hash}")
@app.get("/permalink/{media_hash}/{ts_ins}")
async def permalink_top(request: Request, media_hash: str, ts_ins: str = None):
    # We need to know if the url is for a video or a picture!
    posts = [
        {**dict(row), "type": _media_type(row["media"])}
        async for row in QS.topcat.get_posts_for_hash(
            db["cat"], media_hash=media_hash, ts_ins=ts_ins
        )
    ]
    return templates.TemplateResponse(
        request,
        "permalink.html",
        {"media_hash": media_hash, "ts_ins": ts_ins, "posts": posts},
    )


@app.get("/books")
@app.get("/books/{book_category}")
async def get_top_books(request: Request, book_category: str = "Books"):
    title = "Top Books"
    book_categories = [
        c["category"] async for c in QS.books.get_categories_for_top_books(db["books"])
    ]
    top_books = [
        row
        async for row in QS.books.get_top_books_for_category(
            db["books"], category=book_category
        )
    ]
    return templates.TemplateResponse(
        request,
        "books.html",
        {
            "top_books": top_books,
            "title": title,
            "book_categories": book_categories,
        },
    )
