import { test } from "node:test";
import assert from "node:assert/strict";
import { computeFlow, parseEvent, parseTeamStats } from "../scripts/lib/espn.mjs";
import { compactGame, compactStats } from "../scripts/lib/apisports.mjs";
import { mergeSeason } from "../scripts/lib/merge.mjs";
import { matchThreads } from "../scripts/lib/reddit.mjs";
import { boxScore, flowScore, percentileRanker, rewatchScore } from "../scripts/lib/score.mjs";
import { addDays, etDay, seasonKey, seasonLabel } from "../scripts/lib/util.mjs";

const play = (period, clock, homeScore, awayScore) => ({ period: { number: period }, clock: { displayValue: clock }, homeScore, awayScore });

function thrillerPlays() {
  const plays = [];
  for (let i = 0; i < 30; i += 1) plays.push(play(1 + Math.floor(i / 10), "5:00", 10 + i, i % 2 ? 12 + i : 8 + i));
  plays.push(play(4, "4:30", 100, 98), play(4, "1:00", 104, 105), play(4, "0:10", 108, 107), play(4, "0.0", 108, 110));
  return plays;
}

test("seasons and Eastern game days", () => {
  assert.equal(seasonKey("2024-10-22"), "2024");
  assert.equal(seasonKey("2025-04-10"), "2024");
  assert.equal(seasonLabel("2024"), "2024-25");
  assert.equal(seasonLabel("2099"), "2099-00");
  assert.equal(etDay("2025-01-11T02:00:00Z"), "2025-01-10");
  assert.equal(addDays("2025-03-01", -1), "2025-02-28");
});

test("parseEvent keeps real regular-season games and drops preseason/all-star", () => {
  const event = (type, homeId = "1", awayId = "2") => ({
    id: "1", date: "2025-01-11T02:00Z", season: { type }, status: { period: 4, type: { completed: true } },
    competitions: [{ competitors: [
      { homeAway: "home", score: "100", team: { id: homeId, name: "Hawks", displayName: "Atlanta Hawks" } },
      { homeAway: "away", score: "90", team: { id: awayId, name: "Celtics", displayName: "Boston Celtics" } },
    ] }],
  });
  assert.equal(parseEvent(event(2)).day, "2025-01-10");
  assert.equal(parseEvent(event(1)), null);
  assert.equal(parseEvent(event(2, "1", "98")), null);
});

test("parseTeamStats derives percentages from made/attempted", () => {
  const stats = parseTeamStats([
    { name: "fieldGoalsMade-fieldGoalsAttempted", displayValue: "38-91" },
    { name: "threePointFieldGoalsMade-threePointFieldGoalsAttempted", displayValue: "10-38" },
    { name: "assists", displayValue: "25" },
  ], 100);
  assert.equal(stats.fgp, 41.8);
  assert.equal(stats.tpp, 26.3);
  assert.equal(stats.assists, 25);
  assert.equal(stats.points, 100);
});

test("computeFlow counts lead changes, clutch margin and overtime", () => {
  const flow = computeFlow(thrillerPlays(), []);
  assert.ok(flow.leadChanges >= 3);
  assert.equal(flow.finalMargin, 2);
  assert.equal(flow.clutchMargin, 2);
  assert.equal(flow.clutchMin, 0 + 1);
  assert.equal(flow.overtimes, 0);
  assert.equal(computeFlow([], []), null);
});

test("blowouts score far below thrillers", () => {
  const thriller = flowScore({ leadChanges: 14, finalMargin: 2, clutchMargin: 1, clutchMin: 0, overtimes: 1, comebackDeficit: 15, wpTension: 0.6 });
  const blowout = flowScore({ leadChanges: 1, finalMargin: 28, clutchMargin: 26, clutchMin: 22, overtimes: 0, comebackDeficit: 2, wpTension: 0.05 });
  assert.ok(thriller > 85, `thriller ${thriller}`);
  assert.ok(blowout < 10, `blowout ${blowout}`);
});

test("boxScore ignores missing values instead of treating them as zero", () => {
  const team = { points: 120, fgp: 50, tpm: 14, assists: 28, steals: 8, blocks: 5, turnovers: 12 };
  const full = boxScore({ home: team, away: team }, { home: { pts: 40 }, away: { pts: 20 } }, 1);
  const partial = boxScore({ home: { ...team, steals: null }, away: team }, {}, 0);
  assert.ok(full > 60 && full <= 100);
  assert.ok(partial > 40);
});

test("rewatchScore reweights when buzz is unavailable", () => {
  const input = {
    stats: { home: { points: 130, fgp: 52, tpm: 16, assists: 30, steals: 8, blocks: 5, turnovers: 10 }, away: { points: 128, fgp: 51, tpm: 15, assists: 29, steals: 7, blocks: 4, turnovers: 11 } },
    top: { home: { pts: 45 } },
    tripleDoubles: 0,
    flow: { leadChanges: 12, finalMargin: 2, clutchMargin: 2, clutchMin: 0, overtimes: 0, comebackDeficit: 12, wpTension: 0.6 },
  };
  const without = rewatchScore(input, null);
  const withBuzz = rewatchScore(input, 100);
  assert.equal(without.buzz, null);
  assert.ok(withBuzz.score > without.score);
  assert.ok(without.score <= 100 && withBuzz.score <= 100);
});

test("percentileRanker needs enough data", () => {
  assert.equal(percentileRanker([1, 2, 3])(2), null);
  const rank = percentileRanker(Array.from({ length: 50 }, (_, i) => i));
  assert.equal(rank(0), 0);
  assert.equal(rank(49), 100);
});

const espnGame = {
  id: "1", date: "2025-01-11T02:00Z", day: "2025-01-10", seasonType: 2, completed: true, note: null,
  home: { id: "1", abbr: "DEN", name: "Denver Nuggets", nick: "Nuggets", logo: "x", score: 124 },
  away: { id: "2", abbr: "BKN", name: "Brooklyn Nets", nick: "Nets", logo: "y", score: 105 },
  stats: { home: { points: 124, longestRun: null }, away: { points: 105, longestRun: null } },
};

test("mergeSeason fills missing ESPN stats from api-sports and avoids duplicates", () => {
  const apiGame = compactGame({
    id: 9, date: { start: "2025-01-11T02:00:00.000Z" }, stage: 2, status: { short: 3 }, periods: { total: 4 },
    teams: { home: { id: 7, name: "Denver Nuggets", nickname: "Nuggets", code: "DEN" }, visitors: { id: 8, name: "Brooklyn Nets", nickname: "Nets", code: "BKN" } },
    scores: { home: { points: 124 }, visitors: { points: 105 } },
  });
  const stats = compactStats(apiGame, [
    { team: { id: 7 }, statistics: [{ points: 124, longestRun: 11 }] },
    { team: { id: 8 }, statistics: [{ points: 105, longestRun: 8 }] },
  ]);
  const merged = mergeSeason({ espn: { 1: espnGame }, apisports: { games: { 9: apiGame }, stats: { 9: stats } }, reddit: {} });
  assert.equal(merged.length, 1);
  assert.equal(merged[0].stats.home.longestRun, 11);
  assert.deepEqual(merged[0].sources, ["espn", "apisports"]);
});

test("mergeSeason keeps api-sports-only games that have stats", () => {
  const apiGame = compactGame({
    id: 9, date: { start: "2025-01-11T02:00:00.000Z" }, stage: 2, status: { short: 3 }, periods: { total: 5 },
    teams: { home: { id: 7, name: "Denver Nuggets", nickname: "Nuggets", code: "DEN" }, visitors: { id: 8, name: "Brooklyn Nets", nickname: "Nets", code: "BKN" } },
    scores: { home: { points: 124 }, visitors: { points: 122 } },
  });
  const stats = { home: { points: 124 }, away: { points: 122 } };
  const merged = mergeSeason({ espn: {}, apisports: { games: { 9: apiGame }, stats: { 9: stats } }, reddit: {} });
  assert.equal(merged[0].id, "ap9");
  assert.equal(merged[0].home.logo, undefined);
  assert.equal(merged[0].flow.overtimes, 1);
  assert.equal(compactGame({ date: { start: "2023-10-07T16:00:00Z" }, stage: 1 }), null);
});

test("api-sports abbreviations map onto ESPN's so logo files resolve", () => {
  const apiGame = compactGame({
    id: 10, date: { start: "2025-01-11T02:00:00.000Z" }, stage: 2, status: { short: 3 }, periods: { total: 4 },
    teams: { home: { id: 1, name: "Golden State Warriors", nickname: "Warriors", code: "GSW" }, visitors: { id: 2, name: "Utah Jazz", nickname: "Jazz", code: "UTA" } },
    scores: { home: { points: 100 }, visitors: { points: 90 } },
  });
  const stats = { home: { points: 100 }, away: { points: 90 } };
  const [game] = mergeSeason({ espn: {}, apisports: { games: { 10: apiGame }, stats: { 10: stats } }, reddit: {} });
  assert.equal(game.home.abbr, "GS");
  assert.equal(game.away.abbr, "UTAH");
});

test("reddit thread matching uses whole words and the game window", () => {
  const game = { date: "2025-01-11T02:00Z", home: { nick: "Nets", name: "Brooklyn Nets" }, away: { nick: "Hornets", name: "Charlotte Hornets" } };
  const created = Date.parse("2025-01-11T02:30Z");
  const threads = [
    { title: "[Game Thread] Charlotte Hornets (10-20) at Brooklyn Nets (12-18)", created, comments: 4000, score: 300 },
    { title: "[Post Game Thread] The Brooklyn Nets defeat the Charlotte Hornets", created: created + 3 * 3600e3, comments: 1500, score: 900 },
    { title: "[Game Thread] Charlotte Hornets at Miami Heat", created, comments: 5000, score: 10 },
    { title: "[Game Thread] Boston Celtics at Brooklyn Nets", created: created + 5 * 24 * 3600e3, comments: 1, score: 1 },
  ];
  const buzz = matchThreads(threads, game);
  assert.deepEqual(buzz, { live: { comments: 4000, score: 300 }, post: { comments: 1500, score: 900 } });
  assert.equal(matchThreads(threads, { ...game, away: { nick: "Magic", name: "Orlando Magic" } }), null);
});
