-- name: add_indexes#
-- Delete rows we don't need
-- Add indexes
-- Fill percent_ranks and countvotes columns
-- Create full text index

-- Keep the tconst for series and mini series e.g. Friends = tt108778
-- Also keep the all the episode tconst for the ^ series 
CREATE TABLE keep_tconst (tconst text);

INSERT INTO keep_tconst
select tconst from basics 
where titleType in ('tvSeries', 'tvMiniSeries');

INSERT INTO keep_tconst
select episode.tconst
from episode
join keep_tconst
    on episode.parentTconst = keep_tconst.tconst
;

delete from basics where tconst not in (select * from keep_tconst);
delete from episode where tconst not in (select * from keep_tconst);        
delete from ratings where tconst not in (select * from keep_tconst);
drop table keep_tconst;


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
with percentiles as (
    select
        ratings.tconst,
        cast(
            round((
                1-percent_rank() over (
                partition by episode.parentTconst
                order by ratings.averageRating desc,
                         ratings.numVotes desc
            ))*100) as int
        ) as percentile
    from episode
    join ratings using (tconst)
)
update ratings
set percentile = percentiles.percentile
from percentiles
where ratings.tconst = percentiles.tconst;


-- Add number of ratings for shows so we can sort by it with the search box
with countvotes as (
    select
        basics.tconst, sum(ratings.numVotes) as totalvotes
    from episode
    join ratings using (tconst)
    join basics on episode.parentTconst = basics.tconst
    group by episode.parentTconst
)
update basics
set totalvotes = countvotes.totalvotes
from countvotes
where basics.tconst = countvotes.tconst;

CREATE INDEX IF NOT EXISTS
basics_totalvotes_idx
on basics (
        totalvotes
    );


-- create show names full text index
drop table if exists show_names_fts;
CREATE VIRTUAL TABLE show_names_fts
USING fts5(primaryTitle, originalTitle, startYear, endYear, content='basics');
-- populate index
INSERT INTO show_names_fts (rowid, primaryTitle, originalTitle, startYear, endYear)
select rowid, "primaryTitle", "originalTitle", cast("startYear" as text), cast("endYear" as text)
from basics
where titleType in ('tvSeries', 'tvMiniSeries');


VACUUM;
