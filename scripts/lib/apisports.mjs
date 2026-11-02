import { etDay, fetchJson, num } from "./util.mjs";

const BASE = "https://v2.nba.api-sports.io";

export class ApiSportsError extends Error {}

export async function request(endpoint, apiKey) {
  const data = await fetchJson(`${BASE}${endpoint}`, { headers: { "x-apisports-key": apiKey } });
  const errors = Array.isArray(data.errors) ? data.errors : Object.values(data.errors || {});
  if (errors.length) throw new ApiSportsError(errors.join("; "));
  return data.response || [];
}

const side = (team) => ({
  id: team.id,
  name: team.name,
  nick: team.nickname,
  code: team.code,
  logo: team.logo,
});

// stage 1 is preseason; keep regular season (2) and playoffs/play-in (3).
export function compactGame(game) {
  if (!game?.date?.start || game.stage < 2) return null;
  return {
    id: game.id,
    date: game.date.start,
    day: etDay(game.date.start),
    stage: game.stage,
    finished: game.status?.short === 3,
    periods: game.periods?.total ?? null,
    home: { ...side(game.teams.home), score: num(game.scores?.home?.points) },
    away: { ...side(game.teams.visitors), score: num(game.scores?.visitors?.points) },
  };
}

const STAT_KEYS = [
  "points", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "offReb", "defReb", "totReb",
  "assists", "pFouls", "steals", "turnovers", "blocks", "fastBreakPoints", "pointsInPaint",
  "biggestLead", "secondChancePoints", "pointsOffTurnovers", "longestRun",
];

function compactTeamStats(entry) {
  const raw = Array.isArray(entry?.statistics) ? entry.statistics[0] : null;
  if (!raw) return null;
  const stats = Object.fromEntries(STAT_KEYS.map((key) => [key, num(raw[key])]));
  stats.fgp = num(raw.fgp);
  stats.tpp = num(raw.tpp);
  stats.ftp = num(raw.ftp);
  return stats;
}

// Statistics come back as two team entries; map them onto home/away by team id.
export function compactStats(game, response) {
  const byTeam = Object.fromEntries((response || []).map((entry) => [entry.team?.id, compactTeamStats(entry)]));
  const home = byTeam[game.home.id];
  const away = byTeam[game.away.id];
  return home && away ? { home, away } : null;
}

export async function fetchSeasonGames(season, apiKey) {
  const response = await request(`/games?season=${season}`, apiKey);
  return response.map(compactGame).filter(Boolean);
}

export async function fetchGameStats(game, apiKey) {
  const response = await request(`/games/statistics?id=${game.id}`, apiKey);
  return compactStats(game, response);
}
