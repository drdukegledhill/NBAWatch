import { etDay, fetchJson, num } from "./util.mjs";

const BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba";
const KEEP_SEASON_TYPES = new Set([2, 3, 5]); // regular season, playoffs, play-in

const compactDay = (day) => day.replaceAll("-", "");

function isRealTeam(team) {
  const id = Number(team?.id);
  return Number.isInteger(id) && id >= 1 && id <= 30 && !team.isAllStar;
}

function parseCompetitor(competitor) {
  const team = competitor.team || {};
  return {
    id: String(team.id),
    abbr: team.abbreviation,
    name: team.displayName,
    nick: team.name,
    logo: team.logo,
    score: num(competitor.score),
    winner: Boolean(competitor.winner),
  };
}

export function parseEvent(event) {
  const competition = event.competitions?.[0];
  if (!competition) return null;
  const seasonType = event.season?.type;
  if (!KEEP_SEASON_TYPES.has(seasonType)) return null;
  const home = competition.competitors?.find((c) => c.homeAway === "home");
  const away = competition.competitors?.find((c) => c.homeAway === "away");
  if (!home || !away || !isRealTeam(home.team) || !isRealTeam(away.team)) return null;
  const statusType = event.status?.type || {};
  return {
    id: String(event.id),
    date: event.date,
    day: etDay(event.date),
    seasonType,
    completed: Boolean(statusType.completed),
    periods: event.status?.period ?? null,
    note: competition.notes?.[0]?.headline || null,
    home: parseCompetitor(home),
    away: parseCompetitor(away),
  };
}

export async function fetchDay(day) {
  const data = await fetchJson(`${BASE}/scoreboard?dates=${compactDay(day)}&limit=100`);
  return (data.events || []).map(parseEvent).filter(Boolean);
}

function splitMadeAttempted(value) {
  const [made, attempted] = String(value ?? "").split("-").map(Number);
  return [Number.isFinite(made) ? made : null, Number.isFinite(attempted) ? attempted : null];
}

const pct = (made, attempted) => (attempted ? Math.round((made / attempted) * 1000) / 10 : null);

export function parseTeamStats(statistics = [], points = null) {
  const byName = Object.fromEntries(statistics.map((s) => [s.name, s.displayValue]));
  const [fgm, fga] = splitMadeAttempted(byName["fieldGoalsMade-fieldGoalsAttempted"]);
  const [tpm, tpa] = splitMadeAttempted(byName["threePointFieldGoalsMade-threePointFieldGoalsAttempted"]);
  const [ftm, fta] = splitMadeAttempted(byName["freeThrowsMade-freeThrowsAttempted"]);
  return {
    points,
    fgm,
    fga,
    fgp: pct(fgm, fga),
    tpm,
    tpa,
    tpp: pct(tpm, tpa),
    ftm,
    fta,
    ftp: pct(ftm, fta),
    offReb: num(byName.offensiveRebounds),
    defReb: num(byName.defensiveRebounds),
    totReb: num(byName.totalRebounds),
    assists: num(byName.assists),
    steals: num(byName.steals),
    blocks: num(byName.blocks),
    turnovers: num(byName.totalTurnovers ?? byName.turnovers),
    pFouls: num(byName.fouls),
    pointsOffTurnovers: num(byName.turnoverPoints),
    fastBreakPoints: num(byName.fastBreakPoints),
    pointsInPaint: num(byName.pointsInPaint),
    biggestLead: num(byName.largestLead),
  };
}

function parsePlayers(group) {
  const table = group?.statistics?.[0];
  if (!table?.labels || !table.athletes) return [];
  const index = Object.fromEntries(table.labels.map((label, i) => [label, i]));
  return table.athletes
    .map((entry) => {
      const stat = (label) => num(entry.stats?.[index[label]]) ?? 0;
      return {
        name: entry.athlete?.displayName,
        pts: stat("PTS"),
        reb: stat("REB"),
        ast: stat("AST"),
        stl: stat("STL"),
        blk: stat("BLK"),
      };
    })
    .filter((player) => player.name);
}

const isTripleDouble = (p) => [p.pts, p.reb, p.ast, p.stl, p.blk].filter((v) => v >= 10).length >= 3;

export function parsePlayerHighlights(boxscorePlayers = [], teamIdBySide) {
  const sideById = Object.fromEntries(Object.entries(teamIdBySide).map(([side, id]) => [id, side]));
  const top = {};
  let tripleDoubles = 0;
  for (const group of boxscorePlayers) {
    const side = sideById[String(group.team?.id)];
    const players = parsePlayers(group);
    if (!side || !players.length) continue;
    const best = players.reduce((a, b) => (b.pts > a.pts ? b : a));
    top[side] = { name: best.name, pts: best.pts, reb: best.reb, ast: best.ast };
    tripleDoubles += players.filter(isTripleDouble).length;
  }
  return { top, tripleDoubles };
}

function parseClockSeconds(display) {
  if (display === undefined || display === null) return null;
  const text = String(display);
  if (text.includes(":")) {
    const [minutes, seconds] = text.split(":").map(Number);
    return minutes * 60 + seconds;
  }
  const value = Number.parseFloat(text);
  return Number.isFinite(value) ? value : null;
}

const round = (value, digits = 2) => Math.round(value * 10 ** digits) / 10 ** digits;

// Reduces a play-by-play feed (plus optional win probability) to the handful of
// numbers the rewatch score needs, so the raw feed never has to be stored.
export function computeFlow(plays = [], winProbability = []) {
  const scored = plays.filter((p) => Number.isFinite(p.homeScore) && Number.isFinite(p.awayScore));
  if (scored.length < 20) return null;

  let leadChanges = 0;
  let ties = 0;
  let lastLeader = 0;
  let previousMargin = 0;
  let maxHomeLead = 0;
  let maxAwayLead = 0;
  let clutchMargin = null;
  let clutchMin = null;
  let periods = 1;

  for (const play of scored) {
    const margin = play.homeScore - play.awayScore;
    const period = play.period?.number || 1;
    periods = Math.max(periods, period);

    const leader = Math.sign(margin);
    if (leader !== 0) {
      if (lastLeader !== 0 && leader !== lastLeader) leadChanges += 1;
      lastLeader = leader;
    } else if (previousMargin !== 0) {
      ties += 1;
    }
    previousMargin = margin;
    maxHomeLead = Math.max(maxHomeLead, margin);
    maxAwayLead = Math.max(maxAwayLead, -margin);

    const secondsLeft = parseClockSeconds(play.clock?.displayValue);
    if (period >= 4 && secondsLeft !== null && secondsLeft <= 300) {
      if (clutchMargin === null) clutchMargin = Math.abs(margin);
      clutchMin = clutchMin === null ? Math.abs(margin) : Math.min(clutchMin, Math.abs(margin));
    }
  }

  const last = scored[scored.length - 1];
  const finalMargin = last.homeScore - last.awayScore;
  const winnerSign = Math.sign(finalMargin) || 1;
  const winnerDeficit = winnerSign > 0 ? maxAwayLead : maxHomeLead;

  let wpMin = null;
  let wpTension = null;
  if (winProbability.length >= 20) {
    const winnerWp = winProbability.map((w) => (winnerSign > 0 ? w.homeWinPercentage : 1 - w.homeWinPercentage));
    wpMin = round(Math.min(...winnerWp), 3);
    const tail = winProbability.slice(Math.floor(winProbability.length * 0.8));
    wpTension = round(tail.reduce((sum, w) => sum + (1 - Math.abs(2 * w.homeWinPercentage - 1)), 0) / tail.length, 3);
  }

  return {
    leadChanges,
    ties,
    overtimes: Math.max(0, periods - 4),
    finalMargin: Math.abs(finalMargin),
    clutchMargin,
    clutchMin,
    comebackDeficit: winnerDeficit,
    maxLead: [maxHomeLead, maxAwayLead],
    wpMin,
    wpTension,
  };
}

export async function fetchSummary(event) {
  const data = await fetchJson(`${BASE}/summary?event=${event.id}`);
  const teams = data.boxscore?.teams || [];
  const byTeamId = Object.fromEntries(teams.map((t) => [String(t.team?.id), t]));
  const homeBox = byTeamId[event.home.id];
  const awayBox = byTeamId[event.away.id];
  if (!homeBox?.statistics?.length || !awayBox?.statistics?.length) return null;

  const highlights = parsePlayerHighlights(data.boxscore?.players, { home: event.home.id, away: event.away.id });
  return {
    stats: {
      home: parseTeamStats(homeBox.statistics, event.home.score),
      away: parseTeamStats(awayBox.statistics, event.away.score),
    },
    top: highlights.top,
    tripleDoubles: highlights.tripleDoubles,
    flow: computeFlow(data.plays, data.winprobability),
  };
}
