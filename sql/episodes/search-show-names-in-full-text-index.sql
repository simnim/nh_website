-- name: search_show_names_in_full_text_index
-- Search against the show name full text index using the search string.
-- label and value to satisfy https://api.jqueryui.com/autocomplete/#option-source
SELECT
    ( basics.primaryTitle
        || ' ['
        || basics.startYear
        || '-'
        || case when basics.endYear is null then '?' else basics.endYear end
        || '] = tt'
        || printf('%07d', basics.tconst)
    )
        as label,
    'tt'||printf('%07d', basics.tconst) as value
FROM
    show_names_fts(:search_str) fts
    join basics on fts.rowid = basics.rowid
order by totalvotes desc
limit 15
;
