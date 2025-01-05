#!/bin/bash
set -Eeuxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR" && git rev-parse --show-toplevel )"

DB_FILE_LOC="$HOME/imdb.db"

# Hop into a temp directory
pushd $(mktemp -d)

# Create tables
cat ${REPO_DIR}/sql/episodes/create-tables.sql | sqlite3 -echo ${DB_FILE_LOC}

# Download the data
wget https://datasets.imdbws.com/title.basics.tsv.gz
wget https://datasets.imdbws.com/title.episode.tsv.gz
wget https://datasets.imdbws.com/title.ratings.tsv.gz

# Load data into tables
python3 ${REPO_DIR}/cron/imdb_load.py ${DB_FILE_LOC}

# Remove temp files
rm *.tsv.gz

# Add the indexes, computed columns, and delete junk rows
cat ${REPO_DIR}/sql/episodes/add-indexes.sql | sqlite3 -echo ${DB_FILE_LOC}

popd

