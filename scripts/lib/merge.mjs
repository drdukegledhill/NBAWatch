import { gameKey } from "./util.mjs";

const TYPE_BY_ESPN = { 2: "regular", 3: "playoffs", 5: "playin" };

function fillMissing(primary, fallback) {
  if (!fallback) return primary;
  const merged = { ...primary };
  for (const [key, value] of Object.entries(fallback)) {
    if (merged[key] === null || merged[key] === undefined) merged[key] = value;
  }
  return merged;
}

const espnTeam = (team) => ({
  name: team.name,
  nick: team.nick,
  abbr: team.abbr,
  logo: team.logo,
  score: team.score,
});

const apiTeam = (team) => ({
  name: team.name,
  nick: team.nick,
  abbr: team.code,
  logo: team.code ? `https://a.espncdn.com/i/teamlogos/nba/500/${team.code.toLowerCase()}.png` : team.logo,
  score: team.score,
});

// Combines the per-source stores into one record per finished game.
// ESPN is primary (it has plays and player data); api-sports fills gaps and adds
// extra stats; Reddit adds thread counts. api-sports-only games are kept as a fallback.
export function mergeSeason({ espn = {}, apisports = { games: {}, stats: {} }, reddit = {} }) {
  const apiByKey = new Map();
  for (const game of Object.values(apisports.games || {})) {
    if (game.finished) apiByKey.set(gameKey(game.day, game.home.nick, game.away.nick), game);
  }

  const merged = [];
  const used = new Set();

  for (const event of Object.values(espn)) {
    if (!event.completed || !event.stats) continue;
    const key = gameKey(event.day, event.home.nick, event.away.nick);
    const apiGame = apiByKey.get(key);
    const apiStats = apiGame ? apisports.stats?.[apiGame.id] : null;
    if (apiGame) used.add(key);

    merged.push({
      id: event.id,
      day: event.day,
      date: event.date,
      type: TYPE_BY_ESPN[event.seasonType] || "regular",
      note: event.note,
      home: espnTeam(event.home),
      away: espnTeam(event.away),
      stats: {
        home: fillMissing(event.stats.home, apiStats?.home),
        away: fillMissing(event.stats.away, apiStats?.away),
      },
      top: event.top || {},
      tripleDoubles: event.tripleDoubles || 0,
      flow: event.flow || null,
      buzz: reddit[key] || null,
      sources: apiStats ? ["espn", "apisports"] : ["espn"],
    });
  }

  for (const [key, game] of apiByKey) {
    const stats = used.has(key) ? null : apisports.stats?.[game.id];
    if (!stats) continue;
    merged.push({
      id: `ap${game.id}`,
      day: game.day,
      date: game.date,
      type: game.stage === 3 ? "playoffs" : "regular",
      note: null,
      home: apiTeam(game.home),
      away: apiTeam(game.away),
      stats,
      top: {},
      tripleDoubles: 0,
      flow: { overtimes: Math.max(0, (game.periods || 4) - 4), finalMargin: Math.abs(game.home.score - game.away.score) },
      buzz: reddit[key] || null,
      sources: ["apisports"],
    });
  }

  return merged.sort((a, b) => b.date.localeCompare(a.date));
}
