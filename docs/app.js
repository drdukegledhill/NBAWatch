const API_BASE = "https://v2.nba.api-sports.io";
const SEASONS = ["2022", "2023", "2024"];
const CACHE_TTL = 1000 * 60 * 60 * 24 * 7; // 7 days

const elements = {
  apiKey: document.getElementById("apiKey"),
  saveKeyBtn: document.getElementById("saveKeyBtn"),
  seasonSelect: document.getElementById("seasonSelect"),
  getGamesBtn: document.getElementById("getGamesBtn"),
  refreshGamesBtn: document.getElementById("refreshGamesBtn"),
  apiStatus: document.getElementById("apiStatus"),
  cacheStatus: document.getElementById("cacheStatus"),
  cacheProgressBar: document.getElementById("cacheProgressBar"),
  cacheScanStatus: document.getElementById("cacheScanStatus"),
  cacheSeasonBtn: document.getElementById("cacheSeasonBtn"),
  pauseCacheBtn: document.getElementById("pauseCacheBtn"),
  stopCacheBtn: document.getElementById("stopCacheBtn"),
  gameSelect: document.getElementById("gameSelect"),
  getStatsBtn: document.getElementById("getStatsBtn"),
  refreshStatsBtn: document.getElementById("refreshStatsBtn"),
  rankingsBtn: document.getElementById("rankingsBtn"),
  clearCacheBtn: document.getElementById("clearCacheBtn"),
  team1Logo: document.getElementById("team1Logo"),
  team2Logo: document.getElementById("team2Logo"),
  team1Name: document.getElementById("team1Name"),
  team2Name: document.getElementById("team2Name"),
  team1Header: document.getElementById("team1Header"),
  team2Header: document.getElementById("team2Header"),
  statsTableBody: document.querySelector("#statsTable tbody"),
  rewatchScore: document.getElementById("rewatchScore"),
  rankTableBody: document.querySelector("#rankTable tbody"),
  gameView: document.getElementById("gameView"),
  rankView: document.getElementById("rankView"),
};

let gamesById = {};
let currentSeason = SEASONS[0];
let cacheQueue = [];
let cacheRunning = false;
let cachePaused = false;
let cacheAbort = false;
let cacheScanTimer = null;
let cacheScanPhase = 0;

const TEAM_ABBR = {
  "Atlanta Hawks": "ATL",
  "Boston Celtics": "BOS",
  "Brooklyn Nets": "BKN",
  "Charlotte Hornets": "CHA",
  "Chicago Bulls": "CHI",
  "Cleveland Cavaliers": "CLE",
  "Dallas Mavericks": "DAL",
  "Denver Nuggets": "DEN",
  "Detroit Pistons": "DET",
  "Golden State Warriors": "GSW",
  "Houston Rockets": "HOU",
  "Indiana Pacers": "IND",
  "LA Clippers": "LAC",
  "L.A. Clippers": "LAC",
  "Los Angeles Clippers": "LAC",
  "LA Lakers": "LAL",
  "L.A. Lakers": "LAL",
  "Los Angeles Lakers": "LAL",
  "Memphis Grizzlies": "MEM",
  "Miami Heat": "MIA",
  "Milwaukee Bucks": "MIL",
  "Minnesota Timberwolves": "MIN",
  "New Orleans Pelicans": "NOP",
  "New Orleans Hornets": "NOP",
  "New York Knicks": "NYK",
  "Oklahoma City Thunder": "OKC",
  "Orlando Magic": "ORL",
  "Philadelphia 76ers": "PHI",
  "Philadelphia Sixers": "PHI",
  "Phoenix Suns": "PHX",
  "Portland Trailblazers": "POR",
  "Portland Trail Blazers": "POR",
  "Sacramento Kings": "SAC",
  "San Antonio Spurs": "SAS",
  "Toronto Raptors": "TOR",
  "Utah Jazz": "UTA",
  "Washington Wizards": "WAS",
};

const STAT_MEANINGS = {
  fastBreakPoints: "Fast Break Points",
  pointsInPaint: "Points in Paint",
  biggestLead: "Biggest Lead",
  secondChancePoints: "Second Chance Points",
  pointsOffTurnovers: "Points Off Turnovers",
  longestRun: "Longest Run",
  points: "Points",
  fgm: "Field Goals Made",
  fga: "Field Goals Attempted",
  fgp: "Field Goal Percentage",
  ftm: "Free Throws Made",
  fta: "Free Throws Attempted",
  ftp: "Free Throw Percentage",
  tpm: "Three-Point Field Goals Made",
  tpa: "Three-Point Field Goals Attempted",
  tpp: "Three-Point Percentage",
  offReb: "Offensive Rebounds",
  defReb: "Defensive Rebounds",
  totReb: "Total Rebounds",
  assists: "Assists",
  pFouls: "Personal Fouls",
  steals: "Steals",
  turnovers: "Turnovers",
  blocks: "Blocks",
  plusMinus: "+/-",
  min: "Minutes Played",
};

function getApiKey() {
  return localStorage.getItem("nbawatch_api_key") || "";
}

function setApiKey(value) {
  localStorage.setItem("nbawatch_api_key", value);
}

function updateApiStatus(text) {
  elements.apiStatus.textContent = text;
}

function updateCacheStatus(text) {
  elements.cacheStatus.textContent = text;
}

function updateCacheProgress(done, total) {
  const percent = total > 0 ? Math.round((done / total) * 100) : 0;
  elements.cacheProgressBar.style.width = `${percent}%`;
}

function cacheKeyGames(season) {
  return `nbawatch_games_${season}`;
}

function cacheKeyStats(gameId) {
  return `nbawatch_stats_${gameId}`;
}

function writeCache(key, data) {
  localStorage.setItem(key, JSON.stringify({ updatedAt: Date.now(), data }));
}

function readCache(key) {
  const raw = localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed.updatedAt || !parsed.data) return null;
    if (Date.now() - parsed.updatedAt > CACHE_TTL) return null;
    return parsed.data;
  } catch (err) {
    return null;
  }
}

function clearCache() {
  Object.keys(localStorage)
    .filter((key) => key.startsWith("nbawatch_"))
    .forEach((key) => localStorage.removeItem(key));
}

async function apiRequest(endpoint) {
  const apiKey = getApiKey();
  if (!apiKey) {
    throw new Error("Missing API key. Add your key to continue.");
  }
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { "x-apisports-key": apiKey },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API error ${response.status}: ${body}`);
  }
  return response.json();
}

function isValidGamesData(data) {
  if (!data || data.errors) return false;
  return Array.isArray(data.response) && data.response.length > 0;
}

function isValidStatsData(data) {
  return data && Array.isArray(data.response) && data.response.length === 2;
}

function setView(view) {
  if (view === "rank") {
    elements.rankView.classList.remove("hidden");
    elements.gameView.classList.add("hidden");
  } else {
    elements.rankView.classList.add("hidden");
    elements.gameView.classList.remove("hidden");
  }
}

function setTeamDisplay(stats) {
  const team1 = stats[0].team || {};
  const team2 = stats[1].team || {};
  elements.team1Name.textContent = team1.name || "Team 1";
  elements.team2Name.textContent = team2.name || "Team 2";
  elements.team1Header.textContent = team1.name || "Team 1";
  elements.team2Header.textContent = team2.name || "Team 2";
  elements.team1Logo.src = team1.logo || fallbackLogo(team1.name);
  elements.team2Logo.src = team2.logo || fallbackLogo(team2.name);
}

function fallbackLogo(name) {
  if (!name) return "";
  const abbr = TEAM_ABBR[name];
  return abbr ? `https://a.espncdn.com/i/teamlogos/nba/500/${abbr}.png` : "";
}

function buildStatDicts(stats) {
  return stats.map((teamStats) => {
    const statistics = teamStats.statistics;
    if (Array.isArray(statistics)) {
      if (statistics.length && typeof statistics[0] === "object" && !statistics[0].type) {
        return statistics[0];
      }
      const statDict = {};
      statistics.forEach((item) => {
        if (item && item.type) {
          statDict[item.type] = item.value;
        }
      });
      return statDict;
    }
    if (statistics && typeof statistics === "object") {
      return statistics;
    }
    return {};
  });
}

function computeRewatchScore(statDicts) {
  const getFloat = (d, key) => {
    const raw = d[key];
    if (raw === null || raw === undefined || raw === "-") return 0;
    const normalized = String(raw).replace("%", "");
    const value = Number.parseFloat(normalized);
    return Number.isFinite(value) ? value : 0;
  };

  const [t1, t2] = statDicts;
  const points = getFloat(t1, "points") + getFloat(t2, "points");
  const assists = getFloat(t1, "assists") + getFloat(t2, "assists");
  const fgPct = (getFloat(t1, "fgp") + getFloat(t2, "fgp")) / 2;
  const tpPct = (getFloat(t1, "tpp") + getFloat(t2, "tpp")) / 2;
  const tpm = getFloat(t1, "tpm") + getFloat(t2, "tpm");
  const steals = getFloat(t1, "steals") + getFloat(t2, "steals");
  const blocks = getFloat(t1, "blocks") + getFloat(t2, "blocks");
  const closeGame = Math.max(0, 10 - Math.abs(getFloat(t1, "points") - getFloat(t2, "points"))) * 2;
  const turnovers = getFloat(t1, "turnovers") + getFloat(t2, "turnovers");
  const hotHand = getFloat(t1, "fgp") > 70 || getFloat(t2, "fgp") > 70 ? 5 : 0;

  let score = 0;
  score += points / 20;
  score += assists / 8;
  score += fgPct / 2;
  score += tpPct / 2;
  score += tpm / 4;
  score += steals / 4;
  score += blocks / 4;
  score += closeGame;
  score -= turnovers / 2;
  score += hotHand;

  return Math.min(100, score);
}

function renderStatsTable(stats) {
  const statDicts = buildStatDicts(stats);
  const keys = new Set();
  statDicts.forEach((dict) => {
    Object.keys(dict).forEach((key) => keys.add(key));
  });
  const sortedKeys = Array.from(keys).sort();

  elements.statsTableBody.innerHTML = "";
  sortedKeys.forEach((key) => {
    const row = document.createElement("tr");
    const labelCell = document.createElement("td");
    labelCell.textContent = STAT_MEANINGS[key] || key;
    row.appendChild(labelCell);

    const value1 = document.createElement("td");
    value1.textContent = statDicts[0][key] ?? "-";
    row.appendChild(value1);

    const value2 = document.createElement("td");
    value2.textContent = statDicts[1][key] ?? "-";
    row.appendChild(value2);

    elements.statsTableBody.appendChild(row);
  });

  const rewatchScore = computeRewatchScore(statDicts);
  elements.rewatchScore.textContent = rewatchScore.toFixed(1);
}

function renderRankings(rankings) {
  elements.rankTableBody.innerHTML = "";
  rankings.forEach((item, index) => {
    const row = document.createElement("tr");
    [index + 1, item.date, item.matchup, item.gameId, item.score.toFixed(1)].forEach((val) => {
      const cell = document.createElement("td");
      cell.textContent = val;
      row.appendChild(cell);
    });
    elements.rankTableBody.appendChild(row);
  });
}

function populateSeasons() {
  elements.seasonSelect.innerHTML = "";
  SEASONS.forEach((season) => {
    const option = document.createElement("option");
    option.value = season;
    option.textContent = season;
    elements.seasonSelect.appendChild(option);
  });
  elements.seasonSelect.value = currentSeason;
}

function populateGames(games) {
  elements.gameSelect.innerHTML = "";
  if (!games.length) {
    const option = document.createElement("option");
    option.textContent = "No games found";
    option.value = "";
    elements.gameSelect.appendChild(option);
    return;
  }

  games.forEach((game) => {
    const home = game?.teams?.home?.name;
    const away = game?.teams?.visitors?.name;
    const dateRaw = typeof game?.date === "object" ? game?.date?.start : game?.date;
    const date = dateRaw ? String(dateRaw).slice(0, 10) : "";
    const option = document.createElement("option");
    option.value = game.id;
    option.textContent = `${date}: ${away} @ ${home}`;
    elements.gameSelect.appendChild(option);
  });
}

async function fetchGames({ force = false } = {}) {
  const season = elements.seasonSelect.value;
  currentSeason = season;
  setView("game");
  elements.rankingsBtn.disabled = true;

  updateApiStatus("API: fetching games...");
  let data = null;
  if (!force) {
    const cached = readCache(cacheKeyGames(season));
    if (cached && isValidGamesData(cached)) {
      data = cached;
      updateApiStatus("API: games loaded from cache");
    }
  }

  if (!data) {
    try {
      data = await apiRequest(`/games?season=${season}`);
      if (!isValidGamesData(data)) {
        updateApiStatus(`API: no games returned for season ${season}`);
        return;
      }
      writeCache(cacheKeyGames(season), data);
      updateApiStatus("API: games loaded");
    } catch (err) {
      updateApiStatus(`API: ${err.message}`);
      return;
    }
  }

  const games = data.response || [];
  gamesById = {};
  games.forEach((game) => {
    if (game.id) gamesById[game.id] = game;
  });
  populateGames(games);
  startCacheScan(Object.keys(gamesById));
}

function startCacheScan(gameIds) {
  stopCacheScan();
  if (!gameIds.length) {
    updateCacheStatus("Stats cache: no games to cache (0%)");
    updateCacheProgress(0, 0);
    return;
  }

  updateCacheStatus(`Stats cache: scanning cached data for season ${currentSeason}...`);
  elements.cacheScanStatus.textContent = "Scanning cache";
  cacheScanPhase = 0;
  cacheScanTimer = setInterval(() => {
    cacheScanPhase = (cacheScanPhase + 1) % 4;
    elements.cacheScanStatus.textContent = `Scanning cache${".".repeat(cacheScanPhase)}`;
  }, 300);

  let done = 0;
  let idx = 0;
  const total = gameIds.length;

  const scanStep = () => {
    const slice = gameIds.slice(idx, idx + 25);
    slice.forEach((id) => {
      const cached = readCache(cacheKeyStats(id));
      if (cached && isValidStatsData(cached)) done += 1;
    });
    idx += slice.length;
    updateCacheProgress(done, total);
    updateCacheStatus(`Stats cache: ${done}/${total} cached for season ${currentSeason} (${Math.round((done / total) * 100)}%)`);

    if (idx < total) {
      requestAnimationFrame(scanStep);
      return;
    }
    stopCacheScan();
    if (done >= total) {
      updateCacheStatus(`Stats cache: all cached for season ${currentSeason} (100%)`);
      elements.rankingsBtn.disabled = false;
    } else {
      elements.rankingsBtn.disabled = true;
    }
  };

  scanStep();
}

function stopCacheScan() {
  if (cacheScanTimer) {
    clearInterval(cacheScanTimer);
    cacheScanTimer = null;
  }
  elements.cacheScanStatus.textContent = "";
}

async function fetchStats(gameId, { force = false } = {}) {
  if (!gameId) {
    updateApiStatus("API: select a valid game");
    return null;
  }

  updateApiStatus(`API: fetching stats for game ${gameId}...`);
  let data = null;
  if (!force) {
    const cached = readCache(cacheKeyStats(gameId));
    if (cached && isValidStatsData(cached)) {
      data = cached;
      updateApiStatus("API: stats loaded from cache");
    }
  }

  if (!data) {
    try {
      data = await apiRequest(`/games/statistics?id=${gameId}`);
      if (isValidStatsData(data)) {
        writeCache(cacheKeyStats(gameId), data);
        updateApiStatus("API: stats loaded");
      } else {
        updateApiStatus("API: stats not ready for this game");
        return null;
      }
    } catch (err) {
      updateApiStatus(`API: ${err.message}`);
      return null;
    }
  }

  return data;
}

async function handleGetStats(force = false) {
  const gameId = elements.gameSelect.value;
  setView("game");
  const data = await fetchStats(gameId, { force });
  if (!data) return;
  setTeamDisplay(data.response);
  renderStatsTable(data.response);
}

function buildRankings() {
  if (!Object.keys(gamesById).length) {
    updateApiStatus("API: load games first");
    return;
  }

  const rankings = [];
  let skipped = 0;
  Object.entries(gamesById).forEach(([gameId, game]) => {
    const cached = readCache(cacheKeyStats(gameId));
    if (!cached || !isValidStatsData(cached)) {
      skipped += 1;
      return;
    }
    const stats = cached.response || [];
    const statDicts = buildStatDicts(stats);
    const score = computeRewatchScore(statDicts);

    const dateRaw = typeof game.date === "object" ? game.date.start : game.date;
    const date = dateRaw ? String(dateRaw).slice(0, 10) : "";
    const home = game?.teams?.home?.name;
    const away = game?.teams?.visitors?.name;
    rankings.push({
      score,
      gameId,
      date,
      matchup: `${away} @ ${home}`,
    });
  });

  rankings.sort((a, b) => b.score - a.score);
  renderRankings(rankings);
  setView("rank");

  if (skipped) {
    updateApiStatus(`API: rankings built for ${currentSeason} (skipped ${skipped} games)`);
  } else {
    updateApiStatus(`API: rankings built for ${currentSeason}`);
  }
}

async function cacheSeasonStats() {
  if (cacheRunning) return;
  const gameIds = Object.keys(gamesById);
  if (!gameIds.length) {
    updateCacheStatus("Stats cache: load games first");
    return;
  }

  cacheQueue = gameIds.filter((id) => {
    const cached = readCache(cacheKeyStats(id));
    return !(cached && isValidStatsData(cached));
  });

  if (!cacheQueue.length) {
    updateCacheStatus(`Stats cache: all cached for season ${currentSeason} (100%)`);
    updateCacheProgress(gameIds.length, gameIds.length);
    elements.rankingsBtn.disabled = false;
    elements.stopCacheBtn.disabled = true;
    elements.pauseCacheBtn.textContent = "Pause";
    return;
  }

  cacheRunning = true;
  cachePaused = false;
  cacheAbort = false;
  elements.pauseCacheBtn.textContent = "Pause";
  elements.stopCacheBtn.disabled = false;

  let done = gameIds.length - cacheQueue.length;
  updateCacheProgress(done, gameIds.length);
  updateCacheStatus(`Stats cache: caching stats for season ${currentSeason}... (${Math.round((done / gameIds.length) * 100)}%)`);

  while (cacheQueue.length && !cacheAbort) {
    if (cachePaused) {
      await delay(300);
      continue;
    }
    const gameId = cacheQueue[0];
    try {
      const data = await fetchStats(gameId, { force: true });
      if (data && isValidStatsData(data)) {
        cacheQueue.shift();
        done += 1;
        updateCacheProgress(done, gameIds.length);
        updateCacheStatus(`Stats cache: cached ${done}/${gameIds.length} games for ${currentSeason} (${Math.round((done / gameIds.length) * 100)}%)`);
      } else {
        await delay(1000);
      }
    } catch (err) {
      updateCacheStatus(`Stats cache: ${err.message}`);
      await delay(2000);
    }
    await delay(650);
  }

  cacheRunning = false;
  elements.stopCacheBtn.disabled = true;
  elements.pauseCacheBtn.textContent = "Pause";
  if (cacheAbort) {
    updateCacheStatus("Stats cache: stopped");
    return;
  }

  updateCacheStatus(`Stats cache: all cached for season ${currentSeason} (100%)`);
  elements.rankingsBtn.disabled = false;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setupEventListeners() {
  elements.saveKeyBtn.addEventListener("click", () => {
    const value = elements.apiKey.value.trim();
    if (value) {
      setApiKey(value);
      updateApiStatus("API: key saved");
      elements.apiKey.value = "";
    }
  });

  elements.seasonSelect.addEventListener("change", () => {
    currentSeason = elements.seasonSelect.value;
  });

  elements.getGamesBtn.addEventListener("click", () => fetchGames({ force: false }));
  elements.refreshGamesBtn.addEventListener("click", () => fetchGames({ force: true }));
  elements.getStatsBtn.addEventListener("click", () => handleGetStats(false));
  elements.refreshStatsBtn.addEventListener("click", () => handleGetStats(true));

  elements.cacheSeasonBtn.addEventListener("click", () => cacheSeasonStats());
  elements.pauseCacheBtn.addEventListener("click", () => {
    if (!cacheRunning) return;
    cachePaused = !cachePaused;
    elements.pauseCacheBtn.textContent = cachePaused ? "Resume" : "Pause";
  });
  elements.stopCacheBtn.addEventListener("click", () => {
    if (!cacheRunning) return;
    cacheAbort = true;
  });

  elements.rankingsBtn.addEventListener("click", () => buildRankings());
  elements.clearCacheBtn.addEventListener("click", () => {
    clearCache();
    updateCacheStatus("Stats cache: cleared local cache");
    updateCacheProgress(0, 0);
    updateApiStatus("API: local cache cleared");
    elements.rankingsBtn.disabled = true;
  });
}

function init() {
  populateSeasons();
  const storedKey = getApiKey();
  if (!storedKey) {
    updateApiStatus("API: missing key (set API key above)");
  }
  elements.rankingsBtn.disabled = true;
  elements.stopCacheBtn.disabled = true;
  setupEventListeners();
}

init();
