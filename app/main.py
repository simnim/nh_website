import mimetypes
import os
import re
import sqlite3
from pathlib import Path

# https://nackjicholson.github.io/aiosql/pydoc/aiosql.html
import aiosql
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

THIS_DIR = Path(__file__).parent

QS = aiosql.from_path(THIS_DIR / "sql", "sqlite3", kwargs_only=True)


def get_sqlite_conn(file_name):
    try:
        # We're just reading... so I think it's safe to share the connection on multiple threads
        conn = sqlite3.connect(os.path.expanduser(file_name), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return None


cat_conn = get_sqlite_conn("~/.top_cat/db")
tv_conn = get_sqlite_conn("~/imdb.db")
books_conn = get_sqlite_conn("~/top-books.db")

app = FastAPI()
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
def show_subpath(request: Request, label: str):
    title = f"Top {label}"
    posts = QS.topcat.get_top_posts_for_flask(cat_conn, label=label)
    # We need to know if the url is for a video or a picture!
    posts = [
        {**post, "type": mimetypes.guess_type(post["media"])[0].split("/")[0]}
        for post in posts
    ]
    return templates.TemplateResponse(
        request, "top-post.html", {"title": title, "posts": posts, "label": label}
    )


def clean_txt(txt):
    "Idempotent: remove special characters, lower case, minimize whitespace"
    no_specials = re.sub(r"[^a-z0-9 ]+", " ", txt.strip().lower())
    return re.sub(r"\s+", " ", no_specials).strip()


def get_search_results_given_search_str(search_str, return_just_id=False):
    # Remove special characters and allow for prefix searches with *
    # Example 'ABC %# ^def & lol'  ->  'abc* AND def* AND lol*'
    query_str = "* AND ".join(clean_txt(search_str).split()) + "*"
    return [
        r["value"] if return_just_id else r["label"]
        for r in QS.episodes.search_show_names_in_full_text_index(
            tv_conn, search_str=query_str
        )
    ]


# Called by the jqueryui autocomplete widget for top-episodes
@app.get("/search")
def search(term: str = ""):
    return get_search_results_given_search_str(search_str=clean_txt(term))


@app.get("/episodes")
@app.get("/episodes/{imdb_show_id}")
@app.get("/episodes/{imdb_show_id}/{max_rank_pct}")
def get_top_episodes_for_show(
    request: Request, imdb_show_id: str = None, max_rank_pct: int = 20
):
    imdb_show_id_int = int(imdb_show_id.lstrip("t")) if imdb_show_id else None
    show_meta = QS.episodes.get_basic_show_info(tv_conn, imdb_show_id=imdb_show_id_int)
    seasons = QS.episodes.get_seasons_summary(tv_conn, imdb_show_id=imdb_show_id_int)
    episodes = QS.episodes.get_top_episodes_for_show(
        tv_conn, imdb_show_id=imdb_show_id_int, max_rank_pct=max_rank_pct
    )
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
def post_top_episodes_for_show(
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
                get_search_results_given_search_str(
                    clean_imdb_id_input, return_just_id=True
                )
                or [None]
            )[0]
        # Build redirect URL
        if clean_imdb_id:
            url = f"/episodes/{clean_imdb_id}/{max_rank_pct_form or 20}"
        else:
            url = "/episodes"
        return RedirectResponse(url=url, status_code=303)
    return RedirectResponse(url="/episodes", status_code=303)


# Just fetch the most recent 10 top posts
@app.get("/permalink/{media_hash}")
@app.get("/permalink/{media_hash}/{ts_ins}")
def permalink_top(request: Request, media_hash: str, ts_ins: str = None):
    posts = QS.topcat.get_posts_for_hash(cat_conn, media_hash=media_hash, ts_ins=ts_ins)
    # We need to know if the url is for a video or a picture!
    posts = [
        {**post, "type": mimetypes.guess_type(post["media"])[0].split("/")[0]}
        for post in posts
    ]
    return templates.TemplateResponse(
        request,
        "permalink.html",
        {"media_hash": media_hash, "ts_ins": ts_ins, "posts": posts},
    )


@app.get("/books")
@app.get("/books/{book_category}")
def get_top_books(request: Request, book_category: str = "Books"):
    title = "Top Books"
    book_categories = [
        c["category"] for c in QS.books.get_categories_for_top_books(books_conn)
    ]
    top_books = QS.books.get_top_books_for_category(books_conn, category=book_category)
    return templates.TemplateResponse(
        request,
        "books.html",
        {
            "top_books": top_books,
            "title": title,
            "book_categories": book_categories,
        },
    )
