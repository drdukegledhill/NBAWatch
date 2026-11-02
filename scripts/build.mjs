import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { DATA_DIR, OUT_DIR, readJson, seasonLabel, storePath, writeJson } from "./lib/util.mjs";
import { mergeSeason } from "./lib/merge.mjs";
import { buzzValue, percentileRanker, rewatchScore } from "./lib/score.mjs";

function seasonsOnDisk() {
  const seasons = new Set();
  for (const source of ["espn", "apisports", "reddit"]) {
    const dir = join(DATA_DIR, source);
    if (!existsSync(dir)) continue;
    for (const file of readdirSync(dir)) {
      if (/^\d{4}\.json$/.test(file)) seasons.add(file.slice(0, 4));
    }
  }
  return [...seasons].sort();
}

export function scoreGames(games) {
  const withBuzz = games.map((game) => ({ game, value: buzzValue(game.buzz) }));
  const rank = percentileRanker(withBuzz.map((entry) => entry.value));
  return withBuzz
    .map(({ game, value }) => ({ ...game, rewatch: rewatchScore(game, rank(value)) }))
    .filter((game) => game.rewatch);
}

export function buildSeason(season) {
  const espn = readJson(storePath("espn", season), { games: {} }).games;
  const apisports = readJson(storePath("apisports", season), { games: {}, stats: {} });
  const reddit = readJson(storePath("reddit", season), { threads: {} }).threads;
  const games = scoreGames(mergeSeason({ espn, apisports, reddit }));
  const outPath = join(OUT_DIR, `${season}.json`);
  const previous = readJson(outPath, null);
  // Keep the file byte-identical when nothing changed so scheduled runs don't create empty commits.
  if (!previous || JSON.stringify(previous.games) !== JSON.stringify(games)) {
    writeJson(outPath, { season: { key: season, label: seasonLabel(season) }, generatedAt: new Date().toISOString(), games });
  }
  return games;
}

export function buildAll() {
  const seasons = [];
  for (const season of seasonsOnDisk()) {
    const games = buildSeason(season);
    if (!games.length) continue;
    seasons.push({
      key: season,
      label: seasonLabel(season),
      games: games.length,
      latest: games[0].day,
    });
    console.log(`build: ${seasonLabel(season)} -> ${games.length} games`);
  }
  seasons.reverse();
  const indexPath = join(OUT_DIR, "index.json");
  const previous = readJson(indexPath, null);
  if (!previous || JSON.stringify(previous.seasons) !== JSON.stringify(seasons)) {
    writeJson(indexPath, { generatedAt: new Date().toISOString(), seasons });
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) buildAll();
