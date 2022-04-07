-- name: get_posts_for_hash
-- Fetches posts for a given media file media_hash. Optionally with a timestamp.
select
      p.url as media
    , p.title
    , p.ts_ins as posted_at
    , p.media_hash as media_hash
    , group_concat( 'top-' || tp.label || ' @ ' || tp.ts_ins , ' || ') as top_labels
from
    post p
    left join top_post tp using (post_id)
where
      p.media_hash = :media_hash
      and (
            :ts_ins is NULL
            OR p.ts_ins = :ts_ins
          )
group by
      p.url
    , p.title
    , p.ts_ins
    , p.media_hash

order by tp.ts_ins asc
;
