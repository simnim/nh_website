#!/bin/bash
set -Eeuxo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

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
ls *.tsv | csv-to-sqlite -D -t full -x$'\t' -o ~/imdb.db

# Remove temp files
rm *.tsv

popd

# Add the indexes and show ranks
cat ${SCRIPT_DIR}/sql/add-indexes-and-ranks.sql | sqlite3 ~/imdb.db

