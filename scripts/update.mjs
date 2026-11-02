import {
  addDays, daysBetween, etDay, gameKey, mapPool, parseArgs, readJson, seasonKey, sleep, storePath, writeJson,
} from "./lib/util.mjs";
import * as espn from "./lib/espn.mjs";
import * as apisports from "./lib/apisports.mjs";
import * as reddit from "./lib/reddit.mjs";
import { buildAll } from "./build.mjs";

const args = parseArgs(process.argv.slice(2));
const today = etDay(new Date());
const to = args.to || today;
const from = args.from || addDays(to, -(Number(args.days) || 3) + 1);
const sources = new Set(String(args.sources || "espn,apisports,reddit").split(","));
const concurrency = Number(args.concurrency) || 4;
const apiBudget = Number(args["apisports-budget"] ?? 30);

const stores = new Map();
const dirty = new Set();

function getStore(source, season, empty) {
  const key = `${source}/${season}`;
  if (!stores.has(key)) stores.set(key, readJson(storePath(source, season), empty));
  dirty.add(key);
  return stores.get(key);
}

function saveAll() {
  for (const key of dirty) {
    const [source, season] = key.split("/");
    writeJson(storePath(source, season), stores.get(key));
  }
}

async function updateEspn() {
  const days = daysBetween(from, to);
  console.log(`espn: scanning ${days.length} day(s) ${from} -> ${to}`);
  let failedDays = 0;
  await mapPool(days, concurrency, async (day) => {
    try {
      const events = await espn.fetchDay(day);
      for (const event of events.filter((e) => e.completed)) {
        const { games } = getStore("espn", seasonKey(event.day), { games: {} });
        games[event.id] = { ...games[event.id], ...event };
      }
    } catch (error) {
      failedDays += 1;
      console.warn(`espn: ${day} failed: ${error.message}`);
    }
  });

  const pending = [];
  for (const key of stores.keys()) {
    if (!key.startsWith("espn/")) continue;
    for (const game of Object.values(stores.get(key).games)) {
      if (game.day >= from && game.day <= to && !game.stats && !game.noStats) pending.push(game);
    }
  }
  console.log(`espn: fetching ${pending.length} game summaries`);

  let done = 0;
  await mapPool(pending, concurrency, async (game) => {
    try {
      const detail = await espn.fetchSummary(game);
      if (detail) {
        Object.assign(game, detail);
      } else {
        game.missing = (game.missing || 0) + 1;
        if (game.missing >= 3) game.noStats = true;
      }
    } catch (error) {
      if (error.message.includes("HTTP 404")) {
        game.missing = (game.missing || 0) + 1;
        if (game.missing >= 3) game.noStats = true;
      }
      console.warn(`espn: summary ${game.id} failed: ${error.message}`);
    }
    done += 1;
    if (done % 50 === 0) {
      saveAll();
      console.log(`espn: ${done}/${pending.length}`);
    }
  });
  if (failedDays === days.length) process.exitCode = 1;
}

async function updateApisports() {
  const apiKey = process.env.NBAWATCH_API_KEY;
  if (!apiKey || apiKey === "YOUR_API_KEY") {
    console.log("apisports: no NBAWATCH_API_KEY, skipping");
    return;
  }
  let budget = apiBudget;
  for (const season of new Set([seasonKey(from), seasonKey(to)])) {
    const store = getStore("apisports", season, { games: {}, stats: {} });
    try {
      const stale = !store.fetchedAt || Date.now() - Date.parse(store.fetchedAt) > 20 * 60 * 60 * 1000;
      if (stale && budget > 0) {
        for (const game of await apisports.fetchSeasonGames(season, apiKey)) store.games[game.id] = game;
        store.fetchedAt = new Date().toISOString();
        budget -= 1;
      }
      const candidates = Object.values(store.games)
        .filter((g) => g.finished && g.day >= from && g.day <= to && store.stats[g.id] === undefined)
        .sort((a, b) => b.date.localeCompare(a.date))
        .slice(0, Math.max(0, budget));
      console.log(`apisports ${season}: fetching stats for ${candidates.length} game(s)`);
      for (const game of candidates) {
        store.stats[game.id] = await apisports.fetchGameStats(game, apiKey);
        budget -= 1;
        await sleep(6500); // free plan allows 10 requests/minute
      }
    } catch (error) {
      console.warn(`apisports ${season}: ${error.message}`);
    }
  }
}

async function updateReddit() {
  if (!reddit.hasCredentials()) {
    console.log("reddit: no REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET, skipping");
    return;
  }
  const threads = await reddit.fetchRecentThreads();
  const cutoff = addDays(today, -7);
  let matched = 0;
  for (const season of new Set([seasonKey(cutoff), seasonKey(today)])) {
    const { games } = getStore("espn", season, { games: {} });
    const store = getStore("reddit", season, { threads: {} });
    for (const game of Object.values(games)) {
      if (game.day < cutoff) continue;
      const buzz = reddit.matchThreads(threads, game);
      if (!buzz) continue;
      store.threads[gameKey(game.day, game.home.nick, game.away.nick)] = buzz;
      matched += 1;
    }
  }
  console.log(`reddit: ${threads.length} threads fetched, ${matched} games matched`);
}

try {
  if (sources.has("espn")) await updateEspn();
  if (sources.has("apisports")) await updateApisports();
  if (sources.has("reddit")) {
    try {
      await updateReddit();
    } catch (error) {
      console.warn(`reddit: ${error.message}`);
    }
  }
} finally {
  saveAll();
}
if (!args["no-build"]) buildAll();
