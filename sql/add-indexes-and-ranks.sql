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

-- Add percent_rank and index so we can get top episodes fast
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

-- Add number of ratings for shows
alter table basics add column totalvotes int;
with countvotes as (
    select
        b.tconst, sum(r.numVotes) as totalvotes
    from episode e
    join ratings r using (tconst)
    join basics b on e.parentTconst = b.tconst
    group by e.parentTconst
)
update basics
set totalvotes = countvotes.totalvotes * 100
from countvotes
where basics.tconst = countvotes.tconst;

CREATE INDEX IF NOT EXISTS
basics_totalvotes_idx
on basics (
        totalvotes
    );

-- create show names full text index
CREATE VIRTUAL TABLE show_names_fts
USING fts5(primaryTitle, originalTitle, content='basics');

-- populate index
INSERT INTO show_names_fts (rowid, primaryTitle, originalTitle)
select rowid, "primaryTitle", "originalTitle"
from basics
where titleType = 'tvSeries';
