import mimetypes
import os
import sqlite3

import aiosql
from flask import Flask, render_template
from flask_mobility import Mobility

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
Mobility(app)


@app.route("/")
@app.route("/index")
@app.route("/episodes")
@app.route("/episodes/<string:imdb_show_id>/<int:max_rank_pct>")
def only_powerful_episodes(imdb_show_id=None, max_rank_pct=20):
    # For now just query for tt0112178 = star trek voyager and percent to keep of 20
    print("got here")
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
    )
