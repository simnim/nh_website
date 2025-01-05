-- name: get_top_episodes_for_show
-- Fetches the top ranked episodes for a show in canonical order.
SELECT
    episode.seasonNumber,
    episode.episodeNumber,
    basics.primaryTitle,
    ratings.averageRating,
    ratings.numVotes,
    ratings.percent_rank
FROM episode
    JOIN ratings using (tconst)
    JOIN basics using (tconst)
WHERE episode.parentTconst = :imdb_show_id
  AND ratings.percent_rank <= :max_rank_pct
ORDER BY
    episode.seasonNumber,
    episode.episodeNumber
;
