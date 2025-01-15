-- name: get_basic_show_info^
-- Fetches basic metadata about the show.

SELECT
    basics.primaryTitle,
    basics.startYear,
    basics.endYear,
    basics.runtimeMinutes,
    basics.genres
FROM
    basics
WHERE
    tconst = :imdb_show_id
;
