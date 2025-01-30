-- name: get_posts_for_hash
-- Fetches posts for a given media file media_hash. Optionally with a timestamp.
select
    post.url as media,
    post.title,
    post.ts_ins as posted_at,
    post.media_hash,
    group_concat(
        'top-'
        || top_post.label
        || ' @ '
        || top_post.ts_ins,
        ' || '
    ) as top_labels
from
    post
left join
    top_post
    on post.post_id = top_post.post_id
where
    post.media_hash = :media_hash
    and (
        :ts_ins is NULL
        or
        post.ts_ins = :ts_ins
    )
group by
    post.url,
    post.title,
    post.ts_ins,
    post.media_hash
order by
    post.ts_ins desc;
