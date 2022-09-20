-- name: get_top_books_for_category
-- Query for pulling in top_books for a category
select
    *
from
    top_books tb
    join books b using (book_id)
where
    category = :category
order by
    latest_top_timestampz desc
limit
    -- MAX_SHOW_TOP_BOOKS
    10
;
