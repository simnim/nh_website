# About this page:
This website is explained on https://topcat.app/episodes

## How I load the data:
* Grab tsvs from https://datasets.imdbws.com (via cron/refresh_imdb_data.sh) and load them into a fresh sqlite db using cron/imdb_load.py (pandas chunked TSV load), then build indexes, computed columns (percentile/totalvotes), and a full-text search index via app/sql/episodes/add-indexes.sql.
* To make the show search box I created a full text index of show titles and present a rest api for searching. See flask_nh_site.py to see implementation.
* I also added ranks based on episode ratings and view counts to enable pareto filtering (the main feature of top episodes!)
