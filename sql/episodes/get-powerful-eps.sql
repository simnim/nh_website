-- name: get_top_episodes_for_show
-- Fetches the top ranked episodes for a show in canonical order.
SELECT
    episode.seasonnumber,
    episode.episodenumber,
    basics.primarytitle,
    ratings.averagerating,
    ratings.numvotes,
    ratings.percentile
FROM episode
INNER JOIN ratings ON episode.tconst = ratings.tconst
INNER JOIN basics ON episode.tconst = basics.tconst
WHERE
    episode.parenttconst = :imdb_show_id
    AND ratings.percentile >= (100 - :max_rank_pct)
ORDER BY
    episode.seasonnumber,
    episode.episodenumber;
