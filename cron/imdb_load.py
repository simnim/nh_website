#!/usr/bin/env python3
import sys

import pandas as pd
from sqlalchemy import create_engine

# from sqlalchemy import text as sql_text
# with db_engine.connect() as connection:
#     for sql in """
#         """.split(';'):
#         connection.execute(sql_text(sql))


if len(sys.argv) != 2:
    print(f"Usage: {sys.argv[0]} <path-to-destination-sqlite-db>", file=sys.stderr)
    sys.exit(1)

db_engine = create_engine(f"sqlite:///{sys.argv[1]}")


FILE_TABLE_MAP = {
    "title.basics.tsv.gz": "basics",
    "title.episode.tsv.gz": "episode",
    "title.ratings.tsv.gz": "ratings",
}

for fname, table_name in FILE_TABLE_MAP.items():
    try:
        for df in pd.read_csv(fname, sep="\t", dtype=str, na_values="\\N", chunksize=10_000):
            for tcol in ["tconst", "parentTconst"]:
                if tcol in df:
                    df[tcol] = df[tcol].str.removeprefix("tt")
            df.to_sql(table_name, db_engine, if_exists="append", index=False)
    except Exception as e:
        print(
            f"ERROR: failed loading {fname!r} into table {table_name!r}: {e}",
            file=sys.stderr,
        )
        raise
