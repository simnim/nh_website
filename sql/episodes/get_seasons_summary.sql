-- name: get_seasons_summary
-- Fetches the top ranked episodes for a show in canonical order.
SELECT
    episode.seasonNumber,
    round(avg(ratings.averageRating),2) as average_rating,
    cast(avg(ratings.numVotes) as int) as average_num_votes,
    cast(avg(ratings.percentile) as int) as average_percentile
FROM episode
    JOIN ratings using (tconst)
    JOIN basics using (tconst)
-- WHERE episode.parentTconst = 312172  -- monk
WHERE episode.parentTconst = :imdb_show_id
group by episode.seasonNumber
ORDER BY
   average_percentile desc
--, episode.seasonNumber
;
