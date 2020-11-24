-- name: add_indexes_and_ranks#
CREATE INDEX IF NOT EXISTS
episode_tconst_idx
on episode (
        tconst
    );

CREATE INDEX IF NOT EXISTS
episode_parentTconst_idx
on episode (
        parentTconst
    );

CREATE INDEX IF NOT EXISTS
basics_tconst_idx
on basics (
        tconst
    );

CREATE INDEX IF NOT EXISTS
ratings_tconst_idx
on ratings (
        tconst
    );


alter table ratings add column percent_rank float;
with percent_ranks as (
    select
        r.tconst,
        percent_rank() over (
            partition by e.parentTconst
            order by r.averageRating desc,
                     r.numVotes desc
        ) as pct_rnk
    from episode e
    join ratings r using (tconst)
)
update ratings
set percent_rank = percent_ranks.pct_rnk * 100
from percent_ranks
where ratings.tconst = percent_ranks.tconst;

