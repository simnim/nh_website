-- name: get_seasons_summary
-- Fetches the top ranked episodes for a show in canonical order.
SELECT
    episode.seasonnumber,
    cast(avg(ratings.numvotes) AS int) AS average_num_votes,
    cast(avg(ratings.percentile) AS int) AS average_percentile,
    round(avg(ratings.averagerating), 2) AS average_rating
FROM episode
INNER JOIN ratings ON episode.tconst = ratings.tconst
INNER JOIN basics ON episode.tconst = basics.tconst
-- WHERE episode.parentTconst = 312172  -- monk
WHERE episode.parenttconst = :imdb_show_id
GROUP BY episode.seasonnumber
ORDER BY
    average_percentile DESC;
--, episode.seasonNumber
