-- name: get_basic_show_info^
-- Fetches basic metadata about the show.

SELECT
    basics.primarytitle,
    basics.startyear,
    basics.endyear,
    basics.runtimeminutes,
    basics.genres
FROM
    basics
WHERE
    basics.tconst = :imdb_show_id;
