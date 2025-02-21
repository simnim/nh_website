import mimetypes
import os
import re
import sqlite3
import sys

import aiosql
from flask import Flask, redirect, render_template, request, url_for
from flask_mobility import Mobility
from flask_restful import Api, Resource
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField

THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

CATS_DB_FILE_LOC = "~/.top_cat/db"
# We're just reading... so I think it's safe to share the connection on multiple threads
cat_conn = sqlite3.connect(
    os.path.expanduser(CATS_DB_FILE_LOC), check_same_thread=False
)
cat_conn.row_factory = sqlite3.Row

EPS_DB_FILE_LOC = "~/imdb.db"
# We're just reading... so I think it's safe to share the connection on multiple threads
tv_conn = sqlite3.connect(os.path.expanduser(EPS_DB_FILE_LOC), check_same_thread=False)
tv_conn.row_factory = sqlite3.Row

BOOKS_DB_FILE = "~/top-books.db"
# We're just reading... so I think it's safe to share the connection on multiple threads
books_conn = sqlite3.connect(os.path.expanduser(BOOKS_DB_FILE), check_same_thread=False)
books_conn.row_factory = sqlite3.Row

ALL_QUERIES = aiosql.from_path(THIS_SCRIPT_DIR + "/sql", "sqlite3")
CAT_QS = ALL_QUERIES.topcat
TV_QS = ALL_QUERIES.episodes
BOOKS_QS = ALL_QUERIES.books

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
    posts = CAT_QS.get_top_posts_for_flask(cat_conn, label=label)
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
    "lower case and remove special characters"
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", txt.strip().lower())).strip()


def get_search_results_given_search_str(search_str, return_just_id=False):
    # Remove special characters and allow for prefix searches with *
    # Example 'ABC %# ^def & lol'  ->  'abc* AND def* AND lol*'
    query_str = "* AND ".join(clean_txt(search_str).split()) + "*"
    return [
        r["value"] if return_just_id else r["label"]
        for r in TV_QS.search_show_names_in_full_text_index(
            tv_conn, search_str=query_str
        )
    ]


# Called by the jqueryui autocomplete widget for top-episodes
class Searcher(Resource):
    def get(self):
        return get_search_results_given_search_str(request.args["term"])


api.add_resource(Searcher, "/search")


@app.route("/episodes", methods=["GET", "POST"])
@app.route("/episodes/<string:imdb_show_id>", methods=["GET", "POST"])
@app.route(
    "/episodes/<string:imdb_show_id>/<int:max_rank_pct>", methods=["GET", "POST"]
)
def only_powerful_episodes(imdb_show_id=None, max_rank_pct=20):
    form = IMDbForm()
    if request.method == "POST":
        clean_imdb_id_input = clean_txt(form.imdb_show_id.data)
        if clean_imdb_id_input:
            # They succesfully used the search popup menu: extract out the imdb id
            clean_imdb_id = (
                re.findall("tt[0-9]+", clean_imdb_id_input)
                or re.findall(r"^\d+$", clean_imdb_id_input)
                or [None]
            )[0]
            # OR they didn't choose an entry from the menu, maybe they feel lucky?
            if clean_imdb_id is None and len(clean_imdb_id_input) > 3:
                # In case they eagerly hit enter without selecting a menu item then we
                #  won't get an imdb id, but we'll have a reasonable search str so do
                #  the search anyway and return the first result. I'm feeling lucky.
                clean_imdb_id = (
                    get_search_results_given_search_str(
                        clean_imdb_id_input, return_just_id=True
                    )
                    or [None]
                )[0]
            # At this point either we get an imdb show id or we got None
            return redirect(
                url_for(
                    "only_powerful_episodes",
                    imdb_show_id=clean_imdb_id or None,
                    max_rank_pct=form.max_rank_pct.data or None,
                )
            )
        else:
            return redirect(url_for("only_powerful_episodes"))
    imdb_show_id_int = int(imdb_show_id.lstrip("t")) if imdb_show_id else None
    show_meta = TV_QS.get_basic_show_info(tv_conn, imdb_show_id=imdb_show_id_int)
    seasons = TV_QS.get_seasons_summary(tv_conn, imdb_show_id=imdb_show_id_int)
    episodes = TV_QS.get_top_episodes_for_show(
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
    posts = CAT_QS.get_posts_for_hash(cat_conn, media_hash=media_hash, ts_ins=ts_ins)
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
        c["category"] for c in BOOKS_QS.get_categories_for_top_books(books_conn)
    ]
    top_books = BOOKS_QS.get_top_books_for_category(books_conn, category=book_category)
    return render_template(
        "books.html",
        top_books=top_books,
        title=title,
        book_categories=book_categories,
    )
