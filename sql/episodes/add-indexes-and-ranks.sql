-- name: add_indexes_and_ranks#
-- clean up types from csvs-to-sql then add indexes and the percent_ranks column to ratings.

-- preemptively track ids we want to keep
create table keep_tconst (tconst text);
insert into keep_tconst
select tconst from basics where titleType in ('tvSeries', 'tvMiniSeries');
insert into keep_tconst
select e.tconst
from episode e
join keep_tconst k
    on e.parentTconst = k.tconst
;



-- fix types for episode table
ALTER TABLE episode RENAME TO tmp;
CREATE TABLE "episode" (
    "tconst" int,
    "parentTconst" int,
    "seasonNumber" int,
    "episodeNumber" int
);
insert into episode
select
    cast(trim(tconst, 't') as int),
    cast(trim("parentTconst", 't') as int),
    cast(nullif("seasonNumber",'\N') as int),
    cast(nullif("episodeNumber",'\N') as int)
from tmp t
join keep_tconst k using (tconst);
drop table tmp;

-- fix types for basics table
ALTER TABLE "basics" RENAME TO tmp;
CREATE TABLE "basics" (
  "tconst" int,
  "titleType" TEXT,
  "primaryTitle" TEXT,
  "originalTitle" TEXT,
  "isAdult" INTEGER,
  "startYear" INTEGER,
  "endYear" int,
  "runtimeMinutes" int,
  "genres" TEXT,
  "totalvotes" int  -- added by me
);
insert into "basics"
select
    cast(trim(tconst, 't') as int),
    nullif("titleType", '\N'),
    nullif("primaryTitle", '\N'),
    nullif("originalTitle", '\N'),
    "isAdult",
    "startYear",
    cast(nullif("endYear", '\N') as int),
    cast("runtimeMinutes" as int),
    "genres",
    null
from tmp t
join keep_tconst k using (tconst);
drop table tmp;

-- fix types for ratings table
alter table ratings rename to tmp;
CREATE TABLE "ratings" (
  "tconst" int,
  "averageRating" REAL,
  "numVotes" INTEGER,
  "percent_rank" float -- added by me
);
insert into "ratings"
select
    cast(trim(tconst, 't') as int),
    "averageRating",
    "numVotes",
    null
from tmp t
join keep_tconst k using (tconst);
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

-- Add number of ratings for shows so we can sort by it with the search box
with countvotes as (
    select
        b.tconst, sum(r.numVotes) as totalvotes
    from episode e
    join ratings r using (tconst)
    join basics b on e.parentTconst = b.tconst
    group by e.parentTconst
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
USING fts5(primaryTitle, originalTitle, content='basics');
-- populate index
INSERT INTO show_names_fts (rowid, primaryTitle, originalTitle)
select rowid, "primaryTitle", "originalTitle"
from basics
where titleType in ('tvSeries', 'tvMiniSeries');

drop table keep_tconst;

VACUUM;
