#!/bin/bash
set -Eeuxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "$SCRIPT_DIR" && git rev-parse --show-toplevel )"

DB_FILE_LOC="$HOME/imdb.db"

# Hop into a temp directory
pushd $(mktemp -d)

# Download the data, unzip, and use better names...
wget https://datasets.imdbws.com/title.basics.tsv.gz
wget https://datasets.imdbws.com/title.episode.tsv.gz
wget https://datasets.imdbws.com/title.ratings.tsv.gz
gunzip *.gz
mv title.basics.tsv basics.tsv
mv title.episode.tsv episode.tsv
mv title.ratings.tsv ratings.tsv

# Import the data into a sqlite db
ls *.tsv | csvs-to-sqlite --replace-tables -s $'\t' *.tsv ${DB_FILE_LOC}

# Remove temp files
rm *.tsv

popd

# Add the indexes and show ranks
cat ${REPO_DIR}/sql/episodes/add-indexes-and-ranks.sql | sqlite3 ${DB_FILE_LOC}
