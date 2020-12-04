import os
import sqlite3

import aiosql
from flask import Flask, redirect, render_template, request, url_for
from flask_mobility import Mobility
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField

# from wtforms.validators import DataRequired


class IMDbForm(FlaskForm):
    imdb_show_id = StringField("IMDb Show ID")
    max_rank_pct = IntegerField("Max Rank Percent")
    submit = SubmitField("Show the best episodes")


if hasattr(__builtins__, "__IPYTHON__"):
    THIS_SCRIPT_DIR = os.getcwd()
else:
    THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

DB_FILE_LOC = "~/imdb.db"

# We're just reading... so I think it's safe to share the connection on multiple threads
conn = sqlite3.connect(os.path.expanduser(DB_FILE_LOC), check_same_thread=False)
conn.row_factory = sqlite3.Row
QUERIES = aiosql.from_path(THIS_SCRIPT_DIR + "/sql", "sqlite3")

# Got some great tips from https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-ii-templates

app = Flask(__name__)
app.config["SECRET_KEY"] = "derps"
Mobility(app)


@app.route("/", methods=["GET", "POST"])
@app.route("/index", methods=["GET", "POST"])
@app.route("/episodes", methods=["GET", "POST"])
@app.route("/episodes/<string:imdb_show_id>", methods=["GET", "POST"])
@app.route(
    "/episodes/<string:imdb_show_id>/<int:max_rank_pct>", methods=["GET", "POST"]
)
def only_powerful_episodes(imdb_show_id=None, max_rank_pct=20):
    # For now just query for tt0112178 = star trek voyager and percent to keep of 20
    form = IMDbForm()
    print("derp")
    if request.method == "POST":
        if form.imdb_show_id.data:
            return redirect(
                url_for(
                    "only_powerful_episodes",
                    imdb_show_id=form.imdb_show_id.data or None,
                    max_rank_pct=form.max_rank_pct.data or None,
                )
            )
        else:
            return redirect(url_for("only_powerful_episodes"))
    print("derps")
    show_meta = QUERIES.get_basic_show_info(conn, imdb_show_id=imdb_show_id)
    episodes = QUERIES.get_top_episodes_for_show(
        conn, imdb_show_id=imdb_show_id, max_rank_pct=max_rank_pct
    )
    return render_template(
        "episodes.html",
        imdb_show_id=imdb_show_id,
        max_rank_pct=max_rank_pct,
        show_meta=show_meta,
        episodes=episodes,
        form=form,
    )
