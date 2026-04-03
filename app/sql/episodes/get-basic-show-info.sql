-- name: get_basic_show_info(imdb_show_id)^
-- Fetches basic metadata about the show.

SELECT
    basics.primarytitle,
    basics.startyear,
    basics.endyear,
    basics.runtimeminutes,
    basics.genres,
    basics.label,
    basics.value
FROM
    basics
WHERE
    basics.tconst = :imdb_show_id;
