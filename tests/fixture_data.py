"""
Small, deterministic stand-ins for the three databases the site reads.

The real ones are a 1.6 GB weekly imdb dump plus two scraper outputs that only
exist on the machine running the scrapers, so tests built on them either skip
everywhere else or assert against data that changes under them. These are built
from the app's own DDL where the app owns it (app/sql/episodes/*.sql, so
create-tables.sql and add-indexes.sql get exercised too) and from the shape the
queries require where it does not — top_cat.db and top-books.db are written by
the top-cat repo, so the CREATE statements here are this suite's copy of that
contract and will need updating alongside it.
"""

import sqlite3
from pathlib import Path

EPISODES_SQL_DIR = Path(__file__).resolve().parent.parent / "app" / "sql" / "episodes"

# --------------------------------------------------------------------------
# imdb.db
# --------------------------------------------------------------------------

# Ratings are a fixed permutation rather than random so percentiles, row
# colours and the top/not-top split are identical on every run.
SHOWS = [
    # tconst, title, start, end, runtime, genres, seasons, episodes/season
    (1000001, "Nebula Patrol", 1995, 2001, 45, "Action,Adventure,Sci-Fi", 4, 25),
    (1000002, "Nebula Patrol: Redux", 2015, None, 42, "Sci-Fi", 2, 6),
    (2000003, "Quiet Bakery", 2019, 2019, 30, "Comedy", 1, 4),
    # Titles come out of the imdb dump, which nobody here controls, and they
    # land in half a dozen template slots. This one carries every character
    # that would break out of one, so tests/test_security.py can prove they
    # arrive escaped. Keep it last: episode tconsts are handed out in this
    # order, and inserting above would renumber the shows the other tests pin.
    (3000004, 'Zorbtown <script>alert("xss")</script> & Sons', 2020, 2021, 30, "Comedy", 1, 2),
]

# The show above, by the names the security tests need to refer to it.
XSS_SHOW_TCONST = "tt3000004"
XSS_SHOW_TITLE = SHOWS[-1][1]
XSS_PAYLOAD = '<script>alert("xss")</script>'

# The show every episode-page test drives: 100 episodes is enough rows to
# scroll a frozen header out of a viewport and to leave plenty below a cutoff.
MAIN_SHOW_ID = 1000001
MAIN_SHOW_TITLE = "Nebula Patrol"
MAIN_SHOW_TCONST = "tt1000001"
MAIN_SHOW_LABEL = "Nebula Patrol [1995-2001] = tt1000001"
MAIN_SHOW_EPISODES = 100

# Six episodes a season against a 37-step permutation puts Redux's two season
# averages far apart (22 and 77), which the main show — 25 episodes a season,
# so every season averages out near 50 — cannot do. The seasons row wash clamps
# past a fixed distance from 50, and this is the show that reaches it.
REDUX_SHOW_TCONST = "tt1000002"

# Quiet Bakery ends with an unaired special that imdb lists without season or
# episode numbers — the template has a separate row-id branch for those.
NULL_NUMBERED_SHOW_TCONST = "tt2000003"

_EPISODE_TCONST_BASE = 9000000


def _episode_rows():
    "(tconst, parent, season, episode, title, rating, votes) for every episode."
    tconst = _EPISODE_TCONST_BASE
    for parent, title, start, _end, runtime, genres, seasons, per_season in SHOWS:
        numbered = [(s, e) for s in range(1, seasons + 1) for e in range(1, per_season + 1)]
        slots = numbered + ([(None, None)] if parent == 2000003 else [])
        total = len(slots)
        for idx, (season, episode) in enumerate(slots):
            tconst += 1
            # 37 is coprime with any of the show sizes here, so ratings are a
            # spread-out permutation and no two episodes of a show tie.
            rating = round(5.0 + ((idx * 37) % total) * (5.0 / total), 2)
            name = f"{title} S{season}E{episode}" if season is not None else f"{title} Unaired Special"
            yield (
                tconst,
                parent,
                season,
                episode,
                name,
                rating,
                100 + (idx * 17) % 400,
                start,
                runtime,
                genres,
            )


def build_tv_db(path):
    "imdb.db, built the way cron/refresh_imdb_data.sh builds the real one."
    conn = sqlite3.connect(path)
    try:
        conn.executescript((EPISODES_SQL_DIR / "create-tables.sql").read_text())
        insert_basics = (
            'insert into basics ("tconst", "titleType", "primaryTitle",'
            ' "originalTitle", "isAdult", "startYear", "endYear",'
            ' "runtimeMinutes", "genres") values (?, ?, ?, ?, 0, ?, ?, ?, ?)'
        )
        for tconst, title, start, end, runtime, genres, _s, _e in SHOWS:
            conn.execute(
                insert_basics,
                (tconst, "tvSeries", title, title, start, end, runtime, genres),
            )
        for row in _episode_rows():
            (
                tconst,
                parent,
                season,
                episode,
                name,
                rating,
                votes,
                start,
                runtime,
                genres,
            ) = row
            conn.execute(
                insert_basics,
                (tconst, "tvEpisode", name, name, start, None, runtime, genres),
            )
            conn.execute(
                "insert into episode values (?, ?, ?, ?)",
                (tconst, parent, season, episode),
            )
            conn.execute(
                'insert into ratings ("tconst", "averageRating", "numVotes") values (?, ?, ?)',
                (tconst, rating, votes),
            )
        conn.commit()
        # Percentiles, totalvotes and the search index all come from here, so
        # the fixture exercises the same sql the weekly cron runs.
        conn.executescript((EPISODES_SQL_DIR / "add-indexes.sql").read_text())
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# top_cat.db
# --------------------------------------------------------------------------

CAT_SCHEMA = """
create table post (
      post_id integer primary key
    , url text
    , title text
    , media_hash text
    , ts_ins datetime
);
create table top_post (
      top_post_id integer primary key
    , post_id integer
    , label text
    , ts_ins datetime
);
"""

# A repost: the same media_hash under two post rows, which is the whole point
# of /permalink/{hash} being able to narrow by timestamp.
REPOSTED_HASH = "aaaa1111bbbb2222cccc3333dddd4444eeee5555"
REPOSTED_TS = "2024-03-02 10:00:00"

# url, title, media_hash, ts_ins, label (None = never made top)
CAT_POSTS = [
    (
        "https://i.redd.it/cat01.jpg",
        "A very round cat",
        "hash0000000000000001",
        "2024-03-01 09:00:00",
        "cat",
    ),
    (
        "https://v.redd.it/cat02/DASH_720.mp4",
        "Cat discovers stairs",
        "hash0000000000000002",
        "2024-03-01 10:00:00",
        "cat",
    ),
    # No file extension: mimetypes cannot guess, and the page still has to render.
    (
        "https://www.reddit.com/gallery/cat03",
        "Gallery of cats",
        "hash0000000000000003",
        "2024-03-01 11:00:00",
        "cat",
    ),
    (
        "https://i.redd.it/cat04.png",
        "Cat in a box",
        REPOSTED_HASH,
        "2024-03-01 12:00:00",
        "cat",
    ),
    (
        "https://i.redd.it/cat04.png",
        "Cat in a box (repost)",
        REPOSTED_HASH,
        REPOSTED_TS,
        "cat",
    ),
    (
        "https://i.redd.it/dog01.jpg",
        "Dog greets mailman",
        "hash0000000000000006",
        "2024-03-01 13:00:00",
        "dog",
    ),
    (
        "https://v.redd.it/dog02/DASH_480.mp4",
        "Dog vs sprinkler",
        "hash0000000000000007",
        "2024-03-01 14:00:00",
        "dog",
    ),
    (
        "https://i.redd.it/notatop.jpg",
        "Never made the cut",
        "hash0000000000000008",
        "2024-03-01 15:00:00",
        None,
    ),
]

# /top/{label} is limit 10, so there have to be more than 10 cats to prove it.
CAT_FILLER_COUNT = 12


def build_cat_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(CAT_SCHEMA)
        rows = list(CAT_POSTS)
        for i in range(CAT_FILLER_COUNT):
            rows.append(
                (
                    f"https://i.redd.it/filler{i:02d}.jpg",
                    f"Filler cat {i}",
                    f"hashfiller{i:030d}",
                    f"2024-02-{i + 1:02d} 08:00:00",
                    "cat",
                )
            )
        for post_id, (url, title, media_hash, ts_ins, label) in enumerate(rows, start=1):
            conn.execute(
                "insert into post (post_id, url, title, media_hash, ts_ins) values (?, ?, ?, ?, ?)",
                (post_id, url, title, media_hash, ts_ins),
            )
            if label:
                conn.execute(
                    "insert into top_post (post_id, label, ts_ins) values (?, ?, ?)",
                    (post_id, label, ts_ins),
                )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# top-books.db
# --------------------------------------------------------------------------

BOOKS_SCHEMA = """
create table books (
      book_id integer primary key
    , book_name text
    , book_link text unique
    , author_name text
    , author_link text
    , stars real
    , num_reviews integer
    , book_cover_img text
    , from_url text
    , category text
    , scrape_datetimez datetime
);
create table top_books (
      top_book_id integer primary key
    , book_id integer unique
    , bump_count integer
    , first_top_timestampz datetime
    , latest_top_timestampz datetime
);
create table cache_book_categories (category text);
"""

# The default category in the route is the literal "Books", so one category
# has to be named that or /books renders an empty list.
BOOKS = [
    ("Fixture Tale", "Ada Fixture", "Books"),
    ("Second Fixture Tale", "Ada Fixture", "Books"),
    ("Deep Sea Fixtures", "Bo Sample", "Science"),
]


def build_books_db(path):
    conn = sqlite3.connect(path)
    try:
        conn.executescript(BOOKS_SCHEMA)
        for book_id, (name, author, category) in enumerate(BOOKS, start=1):
            conn.execute(
                "insert into books (book_id, book_name, book_link, author_name,"
                " stars, num_reviews, book_cover_img, category, scrape_datetimez)"
                " values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    book_id,
                    name,
                    f"/dp/fixture{book_id}",
                    author,
                    4.5,
                    100 * book_id,
                    f"https://example.invalid/cover{book_id}.jpg",
                    category,
                    "2024-03-01 00:00:00",
                ),
            )
            conn.execute(
                "insert into top_books (book_id, bump_count, first_top_timestampz,"
                " latest_top_timestampz) values (?, ?, ?, ?)",
                (
                    book_id,
                    book_id,
                    "2024-02-01 00:00:00",
                    f"2024-03-0{book_id} 00:00:00",
                ),
            )
        for category in sorted({category for _n, _a, category in BOOKS}):
            conn.execute("insert into cache_book_categories values (?)", (category,))
        conn.commit()
    finally:
        conn.close()


def build_all(data_dir):
    "Writes the three dbs into `data_dir` under the names the app expects."
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    build_tv_db(data_dir / "imdb.db")
    build_cat_db(data_dir / "top_cat.db")
    build_books_db(data_dir / "top-books.db")
    return data_dir
