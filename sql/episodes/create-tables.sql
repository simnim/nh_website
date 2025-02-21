-- name: create_tables#
-- creates tables ready to load in data

CREATE TABLE "episode" (
    "tconst" int,
    "parentTconst" int,
    "seasonNumber" int,
    "episodeNumber" int
);

CREATE TABLE "basics" (
    "tconst" int,
    "titleType" text,
    "primaryTitle" text,
    "originalTitle" text,
    "isAdult" integer,
    "startYear" integer,
    "endYear" int,
    "runtimeMinutes" int,
    "genres" text,
    "totalvotes" int  -- added by me
);

CREATE TABLE "ratings" (
    "tconst" int,
    "averageRating" real,
    "numVotes" integer,
    -- "percent_rank" float -- added by me
    "percentile" int -- added by me
);
