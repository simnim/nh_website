-- name: add_indexes#
-- Delete rows we don't need
-- Add indexes
-- Fill percent_ranks and countvotes columns
-- Create full text index

-- Keep the tconst for series and mini series e.g. Friends = tt108778
-- Also keep the all the episode tconst for the ^ series
CREATE TABLE keep_tconst (tconst text);

INSERT INTO keep_tconst
SELECT tconst FROM basics
WHERE titletype IN ('tvSeries', 'tvMiniSeries');

INSERT INTO keep_tconst
SELECT episode.tconst
FROM episode
INNER JOIN keep_tconst ON episode.parenttconst = keep_tconst.tconst;

DELETE FROM basics
WHERE tconst NOT IN (SELECT tconst FROM keep_tconst);

DELETE FROM episode
WHERE tconst NOT IN (SELECT tconst FROM keep_tconst);

DELETE FROM ratings
WHERE tconst NOT IN (SELECT tconst FROM keep_tconst);
DROP TABLE keep_tconst;


CREATE INDEX IF NOT EXISTS
episode_tconst_idx
ON episode (tconst);

CREATE INDEX IF NOT EXISTS
episode_parent_tconst_idx
ON episode (parenttconst);

CREATE INDEX IF NOT EXISTS
basics_tconst_idx
ON basics (tconst);

CREATE INDEX IF NOT EXISTS
ratings_tconst_idx
ON ratings (tconst);


-- Add percent_rank and index so we can get top episodes fast
WITH percentiles AS (
    SELECT
        ratings.tconst,
        cast(
            round((
                1 - percent_rank() OVER (
                    PARTITION BY episode.parenttconst
                    ORDER BY
                        ratings.averagerating DESC,
                        ratings.numvotes DESC
                )
            ) * 100) AS int
        ) AS percentile
    FROM episode
    INNER JOIN ratings ON episode.tconst = ratings.tconst
)

UPDATE ratings
SET percentile = percentiles.percentile
FROM percentiles
WHERE ratings.tconst = percentiles.tconst;


-- Add number of ratings for shows so we can sort by it WITH the search box
WITH countvotes AS (
    SELECT
        basics.tconst,
        sum(ratings.numvotes) AS totalvotes
    FROM episode
    INNER JOIN ratings ON episode.tconst = ratings.tconst
    INNER JOIN basics ON episode.parenttconst = basics.tconst
    GROUP BY episode.parenttconst
)

UPDATE basics
SET totalvotes = countvotes.totalvotes
FROM countvotes
WHERE basics.tconst = countvotes.tconst;

CREATE INDEX IF NOT EXISTS
basics_totalvotes_idx
ON basics (totalvotes);


-- create show names full text index
DROP TABLE IF EXISTS show_names_fts;
CREATE VIRTUAL TABLE show_names_fts
USING fts5(primarytitle, originaltitle, startyear, endyear, content='basics'); -- noqa

-- populate index
INSERT INTO show_names_fts (rowid, primaryTitle, originalTitle, startYear, endYear)
SELECT rowid, "primaryTitle", "originalTitle", cast("startYear" AS text), cast("endYear" AS text)
FROM basics
WHERE titleType in ('tvSeries', 'tvMiniSeries');


VACUUM;
