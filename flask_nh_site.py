import mimetypes
import os
import re
import sqlite3
import sys

# https://nackjicholson.github.io/aiosql/pydoc/aiosql.html
import aiosql
from flask import Flask, redirect, render_template, request, url_for
from flask_mobility import Mobility
from flask_restful import Api, Resource
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

QS = aiosql.from_path(THIS_SCRIPT_DIR + "/sql", "sqlite3", kwargs_only=True)


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


# Got some great tips from https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-ii-templates

app = Flask(__name__)
DEFAULT_SECRET = "df9c1bc3-9a9e-4b0c-804f-fa5e27a5572a"
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or DEFAULT_SECRET
if app.config["SECRET_KEY"] == DEFAULT_SECRET:
    print(
        "#WARNING: Using default secret key... please set it before going live",
        file=sys.stderr,
    )
Mobility(app)
api = Api(app)


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"))


@app.route("/")
@app.route("/index")
def index():
    return render_template("index.html")


# Just fetch the most recent 10 top posts
@app.route("/top/<string:label>")
def show_subpath(label):
    title = f"Top {label}"
    posts = QS.topcat.get_top_posts_for_flask(cat_conn, label=label)
    # We need to know if the url is for a video or a picture!
    posts = [
        {**post, "type": mimetypes.guess_type(post["media"])[0].split("/")[0]}
        for post in posts
    ]
    return render_template("top-post.html", title=title, posts=posts, label=label)


class IMDbForm(FlaskForm):
    imdb_show_id = StringField("Show Name Search (or IMDb show ID)")
    max_rank_pct = IntegerField("Show top __% percent (below)")
    submit = SubmitField("Show the best episodes")


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
class Searcher(Resource):
    def get(self):
        return get_search_results_given_search_str(
            search_str=clean_txt(request.args["term"])
        )


api.add_resource(Searcher, "/search")


@app.route("/episodes", methods=["GET", "POST"])
@app.route("/episodes/<string:imdb_show_id>", methods=["GET", "POST"])
@app.route(
    "/episodes/<string:imdb_show_id>/<int:max_rank_pct>", methods=["GET", "POST"]
)
def get_top_episodes_for_show(imdb_show_id=None, max_rank_pct=20):
    form = IMDbForm()
    if request.method == "POST":
        clean_imdb_id_input = clean_txt(form.imdb_show_id.data)
        if clean_imdb_id_input:
            # They succesfully used the search popup menu: extract out the imdb id
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
            # If we got nothing just redirect to episodes index page
            return redirect(
                url_for(
                    "get_top_episodes_for_show",
                    imdb_show_id=clean_imdb_id or None,
                    max_rank_pct=int(form.max_rank_pct.data) or None,
                )
            )
        else:
            return redirect(url_for("get_top_episodes_for_show"))
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
    return render_template(
        "episodes.html",
        imdb_show_id=imdb_show_id,
        max_rank_pct=max_rank_pct,
        show_meta=show_meta,
        episodes=episodes,
        seasons=seasons,
        form=form,
        title=title,
    )


# Just fetch the most recent 10 top posts
@app.route("/permalink/<string:media_hash>", methods=["GET", "POST"])
@app.route("/permalink/<string:media_hash>/<string:ts_ins>", methods=["GET", "POST"])
def permalink_top(media_hash, ts_ins=None):
    posts = QS.topcat.get_posts_for_hash(cat_conn, media_hash=media_hash, ts_ins=ts_ins)
    # We need to know if the url is for a video or a picture!
    posts = [
        {**post, "type": mimetypes.guess_type(post["media"])[0].split("/")[0]}
        for post in posts
    ]
    return render_template(
        "permalink.html", media_hash=media_hash, ts_ins=ts_ins, posts=posts
    )


@app.route("/books")
@app.route("/books/<string:book_category>")
def get_top_books(book_category="Books"):
    title = "Top Books"
    book_categories = [
        c["category"] for c in QS.books.get_categories_for_top_books(books_conn)
    ]
    top_books = QS.books.get_top_books_for_category(books_conn, category=book_category)
    return render_template(
        "books.html",
        top_books=top_books,
        title=title,
        book_categories=book_categories,
    )
