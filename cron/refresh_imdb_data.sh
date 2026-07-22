#!/bin/bash
set -Eeuxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR" && git rev-parse --show-toplevel )"

DB_FILE_PATH="$HOME/.nh-website-data/imdb.db"
CACHE_DIR="$HOME/.nh-website-data/imdb_download_cache"

mkdir -p "$CACHE_DIR"
pushd "$CACHE_DIR"

TEMP_DB_PATH="./imdb.db"

# Download the data (resumable: persistent cache dir + wget -c, so an
# interrupted download picks up where it left off on the next run)
for fname in title.basics.tsv.gz title.episode.tsv.gz title.ratings.tsv.gz; do
    wget -c --tries=5 --retry-connrefused --waitretry=15 --timeout=60 \
        "https://datasets.imdbws.com/${fname}"
    gzip -t "$fname" || { rm -f "$fname"; echo "ERROR: ${fname} failed integrity check, deleted for re-download" >&2; exit 1; }
done

# Rebuild the temp db fresh each run (cheap, and create-tables.sql isn't idempotent)
rm -f "${TEMP_DB_PATH}"

# Create tables
cat "${REPO_DIR}/app/sql/episodes/create-tables.sql" | sqlite3 -echo "${TEMP_DB_PATH}"

# Load data into tables
python3 "${REPO_DIR}/cron/imdb_load.py" "${TEMP_DB_PATH}"

# Remove cached downloads now that they're loaded
# intentionally unquoted: glob must expand to match all three .tsv.gz files
rm *.tsv.gz

# Add the indexes, computed columns, and delete junk rows
cat "${REPO_DIR}/app/sql/episodes/add-indexes.sql" | sqlite3 -echo "${TEMP_DB_PATH}"

mkdir -p "$(dirname "${DB_FILE_PATH}")"
mv "${TEMP_DB_PATH}" "${DB_FILE_PATH}"

popd
