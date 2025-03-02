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
    "totalvotes" int,  -- added by me
    -- for /search via search_show_names_in_full_text_index
    label text AS (
        primarytitle
        || ' ['
        || startyear
        || '-'
        || coalesce(endyear, '?')
        || '] = tt'
        || printf('%07d', tconst)
    ) VIRTUAL,
    value text AS ('tt' || printf('%07d', tconst)) VIRTUAL
);

CREATE TABLE "ratings" (
    "tconst" int,
    "averageRating" real,
    "numVotes" integer,
    -- "percent_rank" float -- added by me
    "percentile" int -- added by me
);
