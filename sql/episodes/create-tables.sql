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

CREATE TABLE "ratings" (
  "tconst" int,
  "averageRating" REAL,
  "numVotes" INTEGER,
  -- "percent_rank" float -- added by me
  "percentile" int -- added by me
);

