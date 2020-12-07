-- name: search_show_names_in_full_text_index
-- Search against the show name full text index using the search string.
-- label and value to satisfy https://api.jqueryui.com/autocomplete/#option-source
SELECT
    b.primaryTitle as label,
    b.tconst as value
FROM
    show_names_fts(
            :search_str
        ) fts
    join basics b on fts.rowid = b.rowid
;
