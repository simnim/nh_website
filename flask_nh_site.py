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

ALL_QUERIES = aiosql.from_path(THIS_SCRIPT_DIR + "/sql", "sqlite3")
CAT_QS = ALL_QUERIES.topcat
TV_QS = ALL_QUERIES.episodes

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
    posts = CAT_QS.get_top_posts_for_flask(cat_conn, label)
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
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", txt.strip().lower()))


# Called by the jqueryui autocomplete widget.
class Searcher(Resource):
    def get(self):
        # Remove special characters and allow for prefix searches with *
        # Example 'ABC %# ^def & lol'  ->  'abc* AND def* AND lol*'
        query_str = "* AND ".join(clean_txt(request.args["term"]).split()) + "*"
        return [
            r["label"]
            for r in TV_QS.search_show_names_in_full_text_index(tv_conn, query_str)
        ]


api.add_resource(Searcher, "/search")


# @app.route("/", methods=["GET", "POST"])
# @app.route("/index", methods=["GET", "POST"])
@app.route("/episodes", methods=["GET", "POST"])
@app.route("/episodes/<string:imdb_show_id>", methods=["GET", "POST"])
@app.route(
    "/episodes/<string:imdb_show_id>/<int:max_rank_pct>", methods=["GET", "POST"]
)
def only_powerful_episodes(imdb_show_id=None, max_rank_pct=20):
    form = IMDbForm()
    if request.method == "POST":
        if form.imdb_show_id.data:
            # extract out imdb id (or None if not provided)
            clean_imdb_id = (
                re.findall("tt[0-9]+", clean_txt(form.imdb_show_id.data)) or [None]
            )[0]
            return redirect(
                url_for(
                    "only_powerful_episodes",
                    imdb_show_id=clean_imdb_id or None,
                    max_rank_pct=form.max_rank_pct.data or None,
                )
            )
        else:
            return redirect(url_for("only_powerful_episodes"))
    show_meta = TV_QS.get_basic_show_info(tv_conn, imdb_show_id=imdb_show_id)
    episodes = TV_QS.get_top_episodes_for_show(
        tv_conn, imdb_show_id=imdb_show_id, max_rank_pct=max_rank_pct
    )
    return render_template(
        "episodes.html",
        imdb_show_id=imdb_show_id,
        max_rank_pct=max_rank_pct,
        show_meta=show_meta,
        episodes=episodes,
        form=form,
    )
