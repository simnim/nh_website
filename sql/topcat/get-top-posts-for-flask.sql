-- name: get_top_posts_for_flask
-- Fetches the most recent 10 posts for a particular label
select
    post.url as media,
    post.title,
    post.ts_ins as noticed_at,
    post.media_hash
from
    top_post
inner join
    post
    on top_post.post_id = post.post_id
where
    top_post.label = :label
order by
    top_post.ts_ins desc
limit
    10;
