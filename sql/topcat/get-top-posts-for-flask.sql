-- name: get_top_posts_for_flask
-- Fetches the most recent 10 posts for a particular label
select
      p.url as media
    , p.title
    , p.ts_ins as noticed_at
    , p.media_hash
from
        top_post tp
    join post p using (post_id)
where tp.label = :label
order by tp.ts_ins desc
limit 10;
