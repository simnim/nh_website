#!/usr/bin/env python3
import sys

import pandas as pd
from sqlalchemy import create_engine

# from sqlalchemy import text as sql_text
# with db_engine.connect() as connection:
#     for sql in """
#         """.split(';'):
#         connection.execute(sql_text(sql))


db_engine = create_engine(f"sqlite:///{sys.argv[1]}")


fname_mapto_table_name = {
    "title.basics.tsv.gz": "basics",
    "title.episode.tsv.gz": "episode",
    "title.ratings.tsv.gz": "ratings",
}

for fname, table_name in fname_mapto_table_name.items():
    for df in pd.read_csv(
        fname, sep="\t", dtype=str, na_values="\\N", chunksize=10_000
    ):
        for tcol in ["tconst", "parentTconst"]:
            if tcol in df:
                df[tcol] = df[tcol].str.replace("t", "")
        df.to_sql(table_name, db_engine, if_exists="append", index=False)
