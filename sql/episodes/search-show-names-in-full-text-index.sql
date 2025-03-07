-- name: search_show_names_in_full_text_index
-- Search against the show name full text index using the search string.
-- label and value to satisfy
-- https://api.jqueryui.com/autocomplete/#option-source
SELECT
    basics.label,
    basics.value
FROM
    show_names_fts(:search_str) AS fts
INNER JOIN basics ON fts.rowid = basics.rowid
ORDER BY basics.totalvotes DESC
LIMIT 15;
