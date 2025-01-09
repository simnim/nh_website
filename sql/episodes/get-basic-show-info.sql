-- name: get_basic_show_info^
-- Fetches basic metadata about the show.

SELECT
    primaryTitle,
    startYear,
    endYear,
    runtimeMinutes,
    genres
FROM
    basics
WHERE
    tconst = :imdb_show_id
;
