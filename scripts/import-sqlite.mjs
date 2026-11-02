// One-off import of the legacy desktop app's SQLite cache into data/apisports/<season>.json.
// Usage: node scripts/import-sqlite.mjs /path/to/nba_cache.sqlite
// Copy the .sqlite file somewhere local first if it lives on a network share.
import { DatabaseSync } from "node:sqlite";
import { compactGame, compactStats } from "./lib/apisports.mjs";
import { readJson, storePath, writeJson } from "./lib/util.mjs";

const dbPath = process.argv[2];
if (!dbPath) {
  console.error("usage: node scripts/import-sqlite.mjs <nba_cache.sqlite>");
  process.exit(1);
}

const db = new DatabaseSync(dbPath, { readOnly: true });
const stores = {};
const gamesById = new Map();

for (const row of db.prepare("SELECT season, json FROM games").all()) {
  const store = (stores[row.season] ||= readJson(storePath("apisports", row.season), { games: {}, stats: {} }));
  for (const raw of JSON.parse(row.json).response || []) {
    const game = compactGame(raw);
    if (!game) continue;
    store.games[game.id] = game;
    gamesById.set(game.id, { game, store });
  }
}

let statsImported = 0;
for (const row of db.prepare("SELECT game_id, json FROM stats").all()) {
  const entry = gamesById.get(row.game_id);
  if (!entry) continue;
  const stats = compactStats(entry.game, JSON.parse(row.json).response);
  if (stats) {
    entry.store.stats[entry.game.id] = stats;
    statsImported += 1;
  }
}

for (const [season, store] of Object.entries(stores)) {
  store.fetchedAt = store.fetchedAt || "2000-01-01T00:00:00.000Z";
  writeJson(storePath("apisports", season), store);
  console.log(`season ${season}: ${Object.keys(store.games).length} games`);
}
console.log(`imported ${statsImported} box scores`);
