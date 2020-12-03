-- name: add_indexes_and_ranks#
-- clean up types from csv-to-sql then add indexes and the percent_ranks column to ratings.

-- fix types for episode table
ALTER TABLE episode RENAME TO tmp;
CREATE TABLE [episode] (
    [tconst] text,
    [parentTconst] text,
    [seasonNumber] int,
    [episodeNumber] int
);
insert into episode
select
    tconst,
    [parentTconst],
    nullif([seasonNumber],'\N'),
    nullif([episodeNumber],'\N')
from tmp;
drop table tmp;


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

