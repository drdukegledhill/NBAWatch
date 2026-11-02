const DATA_DIR = "data";

const el = {
  spoilerToggle: document.getElementById("spoilerToggle"),
  freshness: document.getElementById("freshness"),
  season: document.getElementById("seasonSelect"),
  window: document.getElementById("windowSelect"),
  team: document.getElementById("teamSelect"),
  type: document.getElementById("typeSelect"),
  sort: document.getElementById("sortSelect"),
  status: document.getElementById("status"),
  picksSection: document.getElementById("picksSection"),
  picks: document.getElementById("picks"),
  listTitle: document.getElementById("listTitle"),
  listCount: document.getElementById("listCount"),
  list: document.getElementById("gameList"),
};

const state = { index: null, games: [], percentiles: new Map(), openId: null };

const SORTERS = {
  score: (g) => g.rewatch.score,
  flow: (g) => g.rewatch.flow ?? -1,
  box: (g) => g.rewatch.box ?? -1,
  buzz: (g) => g.rewatch.buzz ?? -1,
};

const STAT_ROWS = [
  ["Points", "points"],
  ["Field goals", "fgm", "fga"],
  ["FG %", "fgp", null, "%"],
  ["3-pointers", "tpm", "tpa"],
  ["3P %", "tpp", null, "%"],
  ["Free throws", "ftm", "fta"],
  ["Rebounds", "totReb"],
  ["Assists", "assists"],
  ["Steals", "steals"],
  ["Blocks", "blocks"],
  ["Turnovers", "turnovers"],
  ["Fast break pts", "fastBreakPoints"],
  ["Points in paint", "pointsInPaint"],
  ["Biggest lead", "biggestLead"],
  ["Longest run", "longestRun"],
  ["Second chance pts", "secondChancePoints"],
];

function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

const spoiler = (text) => h("span", { class: "spoiler" }, text);

function tierFor(percentile) {
  if (percentile >= 90) return { key: "must", label: "Must watch" };
  if (percentile >= 70) return { key: "worth", label: "Worth it" };
  if (percentile >= 30) return { key: "fine", label: "Fine" };
  return { key: "skip", label: "Skip" };
}

function computePercentiles(games) {
  const sorted = games.map((g) => g.rewatch.score).sort((a, b) => a - b);
  state.percentiles = new Map(
    games.map((g) => {
      let below = 0;
      while (below < sorted.length && sorted[below] < g.rewatch.score) below += 1;
      return [g.id, sorted.length > 1 ? (below / (sorted.length - 1)) * 100 : 100];
    }),
  );
}

function ordinalOvertime(n) {
  return n === 1 ? "OT" : `${n}OT`;
}

function tagsFor(game) {
  const tags = [];
  const { flow, top = {} } = game;
  if (flow?.overtimes > 0) tags.push(ordinalOvertime(flow.overtimes));
  if (flow && flow.finalMargin <= 3 && (flow.clutchMin ?? 99) <= 2) tags.push("Down to the wire");
  if (flow?.leadChanges >= 12) tags.push("Back & forth");
  if (flow?.comebackDeficit >= 18) tags.push("Big comeback");
  const bestPoints = Math.max(top.home?.pts ?? 0, top.away?.pts ?? 0);
  if (bestPoints >= 45) tags.push("Scoring explosion");
  if (game.tripleDoubles > 0) tags.push("Triple-double");
  if ((game.rewatch.buzz ?? 0) >= 85) tags.push("Everyone's talking");
  if (game.type === "playoffs") tags.push("Playoffs");
  if (game.type === "playin") tags.push("Play-in");
  return tags;
}

function formatDay(day) {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

function logo(team) {
  return h("img", { class: "logo", src: team.logo, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
}

function matchup(game) {
  return h("div", { class: "matchup" },
    h("span", { class: "team" }, logo(game.away), h("span", {}, game.away.abbr)),
    h("span", { class: "at" }, "@"),
    h("span", { class: "team" }, logo(game.home), h("span", {}, game.home.abbr)),
  );
}

function scoreBadge(game) {
  const tier = tierFor(state.percentiles.get(game.id) ?? 0);
  return h("div", { class: `badge tier-${tier.key}`, title: tier.label },
    h("strong", {}, Math.round(game.rewatch.score)),
    h("span", {}, tier.label),
  );
}

function part(label, value) {
  const known = value !== null && value !== undefined;
  return h("div", { class: "part" },
    h("span", { class: "part-label" }, label),
    h("div", { class: "bar" }, h("div", { class: "bar-fill", style: `width:${known ? value : 0}%` })),
    h("span", { class: "part-value" }, known ? Math.round(value) : "n/a"),
  );
}

function statCell(stats, [, made, attempted, suffix]) {
  const first = stats?.[made];
  if (first === null || first === undefined) return "—";
  if (attempted) return `${first}-${stats[attempted] ?? "?"}`;
  return suffix ? `${first}${suffix}` : String(first);
}

function detail(game) {
  const rows = STAT_ROWS.filter((row) => game.stats.home?.[row[1]] != null || game.stats.away?.[row[1]] != null);
  const table = h("table", { class: "stats" },
    h("thead", {}, h("tr", {}, h("th", {}, "Stat"), h("th", {}, game.away.abbr), h("th", {}, game.home.abbr))),
    h("tbody", {}, rows.map((row) => h("tr", {},
      h("td", {}, row[0]),
      h("td", {}, spoiler(statCell(game.stats.away, row))),
      h("td", {}, spoiler(statCell(game.stats.home, row))),
    ))),
  );

  const performer = (side, team) => game.top?.[side] && h("li", {},
    `${team.abbr}: `,
    spoiler(`${game.top[side].name} — ${game.top[side].pts} pts, ${game.top[side].reb} reb, ${game.top[side].ast} ast`),
  );

  const flow = game.flow;
  const flowFacts = flow && [
    flow.leadChanges !== undefined && h("li", {}, `${flow.leadChanges} lead change${flow.leadChanges === 1 ? "" : "s"}, ${flow.ties} tie${flow.ties === 1 ? "" : "s"}`),
    flow.clutchMargin != null && h("li", {}, `Margin entering the last 5 minutes: ${flow.clutchMargin}`),
    flow.comebackDeficit > 0 && h("li", {}, spoiler(`Winner trailed by as many as ${flow.comebackDeficit}`)),
  ];

  const buzz = game.buzz && h("li", {},
    `r/nba: ${game.buzz.live ? `${game.buzz.live.comments.toLocaleString()} comments in the game thread` : ""}`,
    game.buzz.live && game.buzz.post ? ", " : "",
    game.buzz.post ? `${game.buzz.post.comments.toLocaleString()} in the post-game thread` : "",
  );

  return h("div", { class: "detail" },
    h("div", { class: "detail-col" },
      h("h3", {}, "Why this score"),
      h("div", { class: "parts" },
        part("Box score", game.rewatch.box),
        part("Game flow", game.rewatch.flow),
        part("Fan buzz", game.rewatch.buzz),
      ),
      h("ul", { class: "facts" }, flowFacts, buzz, performer("away", game.away), performer("home", game.home)),
      h("p", { class: "hint" }, `Sources: ${game.sources.join(", ")}`),
    ),
    h("div", { class: "detail-col" }, table),
  );
}

function row(game, rank) {
  const open = state.openId === game.id;
  const tags = tagsFor(game);
  const header = h("button", {
    class: "game-row",
    "aria-expanded": String(open),
    onclick: () => {
      state.openId = open ? null : game.id;
      render();
    },
  },
    h("span", { class: "rank" }, rank),
    h("span", { class: "date" }, formatDay(game.day), game.note ? h("small", {}, game.note) : null),
    matchup(game),
    h("span", { class: "tags" }, tags.slice(0, 4).map((tag) => h("span", { class: "tag" }, tag))),
    h("span", { class: "final" }, spoiler(`${game.away.score}–${game.home.score}`)),
    scoreBadge(game),
  );
  return h("div", { class: `game ${open ? "open" : ""}` }, header, open ? detail(game) : null);
}

function pick(game) {
  return h("button", {
    class: "pick",
    onclick: () => {
      state.openId = game.id;
      render();
      document.getElementById("gameList").scrollIntoView({ behavior: "smooth" });
    },
  },
    h("div", { class: "pick-top" }, matchup(game), scoreBadge(game)),
    h("p", { class: "pick-date" }, formatDay(game.day)),
    h("div", { class: "tags" }, tagsFor(game).slice(0, 3).map((tag) => h("span", { class: "tag" }, tag))),
  );
}

function filteredGames() {
  let games = state.games;
  const windowValue = el.window.value;
  if (windowValue === "latest" && games.length) {
    const latest = games.reduce((max, g) => (g.day > max ? g.day : max), games[0].day);
    games = games.filter((g) => g.day === latest);
  } else if (windowValue !== "all" && games.length) {
    const latest = games.reduce((max, g) => (g.day > max ? g.day : max), games[0].day);
    const cutoff = new Date(`${latest}T12:00:00Z`);
    cutoff.setUTCDate(cutoff.getUTCDate() - Number(windowValue) + 1);
    const cutoffDay = cutoff.toISOString().slice(0, 10);
    games = games.filter((g) => g.day >= cutoffDay);
  }
  if (el.team.value !== "all") games = games.filter((g) => g.home.abbr === el.team.value || g.away.abbr === el.team.value);
  if (el.type.value !== "all") games = games.filter((g) => g.type === el.type.value);

  const sorter = SORTERS[el.sort.value];
  return [...games].sort(sorter ? (a, b) => sorter(b) - sorter(a) : (a, b) => b.date.localeCompare(a.date));
}

function render() {
  const games = filteredGames();
  el.listCount.textContent = `${games.length} game${games.length === 1 ? "" : "s"}`;
  el.list.replaceChildren(...games.map((game, i) => row(game, i + 1)));
  if (!games.length) el.list.append(h("p", { class: "empty" }, "No games match these filters."));

  const picks = [...games].sort((a, b) => b.rewatch.score - a.rewatch.score).slice(0, 3);
  el.picksSection.classList.toggle("hidden", picks.length === 0);
  el.picks.replaceChildren(...picks.map(pick));
}

function populateTeams() {
  const teams = new Map();
  for (const game of state.games) {
    teams.set(game.home.abbr, game.home.name);
    teams.set(game.away.abbr, game.away.name);
  }
  const options = [...teams].sort((a, b) => a[1].localeCompare(b[1]));
  el.team.replaceChildren(
    h("option", { value: "all" }, "All teams"),
    ...options.map(([abbr, name]) => h("option", { value: abbr }, name)),
  );
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Could not load ${path} (${response.status})`);
  return response.json();
}

async function loadSeason(key) {
  el.status.textContent = "Loading season…";
  try {
    const data = await loadJson(`${DATA_DIR}/${key}.json`);
    state.games = data.games;
    state.openId = null;
    computePercentiles(state.games);
    populateTeams();
    el.status.textContent = state.games.length ? "" : "No scored games for this season yet.";
    render();
  } catch (error) {
    el.status.textContent = error.message;
  }
}

function setSpoilerMode(hidden) {
  document.body.classList.toggle("spoilers-hidden", hidden);
  localStorage.setItem("nbawatch_hide_spoilers", hidden ? "1" : "0");
}

async function init() {
  const hidden = localStorage.getItem("nbawatch_hide_spoilers") !== "0";
  el.spoilerToggle.checked = hidden;
  setSpoilerMode(hidden);
  el.spoilerToggle.addEventListener("change", () => setSpoilerMode(el.spoilerToggle.checked));

  document.addEventListener("click", (event) => {
    const target = event.target.closest(".spoiler");
    if (target) target.classList.toggle("revealed");
  });

  for (const control of [el.window, el.team, el.type, el.sort]) control.addEventListener("change", render);
  el.season.addEventListener("change", () => loadSeason(el.season.value));

  try {
    state.index = await loadJson(`${DATA_DIR}/index.json`);
  } catch (error) {
    el.status.textContent = "No data published yet. Run the update workflow first.";
    el.freshness.textContent = "";
    return;
  }
  const latest = state.index.seasons[0]?.latest;
  el.freshness.textContent = latest ? `Latest game day: ${formatDay(latest)}` : "";
  el.season.replaceChildren(...state.index.seasons.map((s) => h("option", { value: s.key }, `${s.label} (${s.games})`)));
  if (state.index.seasons.length) await loadSeason(state.index.seasons[0].key);
}

init();
