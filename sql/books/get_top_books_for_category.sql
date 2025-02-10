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
-- book_cover_img        | https://images-na.ssl-images-amazon.com/images/I/91tQkOHvW9L._AC_UL900_SR900,600_.jpg              -- noqa
-- from_url              | https://www.amazon.com/Best-Sellers-Books-Literature-Fiction/zgbs/books/17/ref=zg_bs_nav_books_1   -- noqa
-- category              | Literature_Fiction
-- scrape_datetimez      | 2022-10-01 23:50:03
select
    top_books.top_book_id,
    top_books.book_id,
    top_books.first_top_timestampz,
    top_books.latest_top_timestampz,
    top_books.bump_count,
    books.book_name,
    books.book_link,
    books.author_name,
    books.author_link,
    books.stars,
    books.num_reviews,
    books.book_cover_img,
    books.from_url,
    books.category,
    books.scrape_datetimez
from
    top_books
inner join books on top_books.book_id = books.book_id
where
    books.category = :category
order by
    top_books.latest_top_timestampz desc
limit
-- MAX_SHOW_TOP_BOOKS
    10;
