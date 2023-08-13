-- name: get_top_books_for_category
-- Query for pulling in top_books for a category
-- top_book_id           | 21301
-- book_id               | 659313
-- first_top_timestampz  | 2022-09-25 02:50:38
-- latest_top_timestampz | 2022-10-01 23:50:03
-- bump_count            | 192
-- book_name             | Fairy Tale
-- book_link             | /Audible-Fairy-Tale/dp/B09R5ZPY6Y
-- author_name           | Stephen King
-- author_link           | <null>
-- stars                 | 4.7
-- num_reviews           | 8232
-- book_cover_img        | https://images-na.ssl-images-amazon.com/images/I/91tQkOHvW9L._AC_UL900_SR900,600_.jpg
-- from_url              | https://www.amazon.com/Best-Sellers-Books-Literature-Fiction/zgbs/books/17/ref=zg_bs_nav_books_1
-- category              | Literature_Fiction
-- scrape_datetimez      | 2022-10-01 23:50:03
select
    top_book_id,
    book_id,
    first_top_timestampz,
    latest_top_timestampz,
    bump_count,
    book_name,
    book_link,
    author_name,
    author_link,
    stars,
    num_reviews,
    book_cover_img,
    from_url,
    category,
    scrape_datetimez
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
