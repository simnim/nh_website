-- name: get_top_episodes_for_show(imdb_show_id, max_rank_pct)
-- Fetches all episodes for a show in canonical order,
-- with a flag for top-percentile episodes.
SELECT
    episode.seasonnumber,
    episode.episodenumber,
    basics.primarytitle,
    ratings.averagerating,
    ratings.numvotes,
    ratings.percentile,
    CASE
        WHEN ratings.percentile >= (100 - :max_rank_pct)
            THEN 1
        ELSE 0
    END AS is_top_episode
FROM episode
INNER JOIN ratings ON episode.tconst = ratings.tconst
INNER JOIN basics ON episode.tconst = basics.tconst
WHERE
    episode.parenttconst = :imdb_show_id
ORDER BY
    episode.seasonnumber ASC NULLS LAST,
    episode.episodenumber ASC NULLS LAST;
