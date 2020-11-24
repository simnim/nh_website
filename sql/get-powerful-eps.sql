-- name: get_top_episodes_for_show
-- Fetches the top ranked episodes for a show in canonical order.
SELECT
    e.seasonNumber,
    e.episodeNumber,
    b.primaryTitle,
    r.averageRating,
    r.numVotes,
    r.percent_rank
FROM episode e
    JOIN ratings r using (tconst)
    JOIN basics b using (tconst)
WHERE e.parentTconst = :imdb_show_id
  AND r.percent_rank <= :max_rank_pct
ORDER BY
    e.seasonNumber,
    e.episodeNumber
;
