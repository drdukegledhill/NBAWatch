import { fetchJson } from "./util.mjs";

const USER_AGENT = "web:nbawatch-data:v1.0 (static dashboard data pipeline)";
const THREAD_WINDOW_MS = 36 * 60 * 60 * 1000;

export function hasCredentials(env = process.env) {
  return Boolean(env.REDDIT_CLIENT_ID && env.REDDIT_CLIENT_SECRET);
}

async function getToken(env) {
  const basic = Buffer.from(`${env.REDDIT_CLIENT_ID}:${env.REDDIT_CLIENT_SECRET}`).toString("base64");
  const data = await fetchJson("https://www.reddit.com/api/v1/access_token", {
    method: "POST",
    headers: {
      Authorization: `Basic ${basic}`,
      "User-Agent": USER_AGENT,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: "grant_type=client_credentials",
  });
  if (!data.access_token) throw new Error("Reddit token request failed");
  return data.access_token;
}

// Game threads and post-game threads from r/nba from the last week (up to 3 pages).
export async function fetchRecentThreads(env = process.env) {
  const token = await getToken(env);
  const threads = [];
  let after = "";
  for (let page = 0; page < 3; page += 1) {
    const query = new URLSearchParams({
      q: '"Game Thread"',
      restrict_sr: "1",
      sort: "new",
      t: "week",
      limit: "100",
    });
    if (after) query.set("after", after);
    const data = await fetchJson(`https://oauth.reddit.com/r/nba/search?${query}`, {
      headers: { Authorization: `Bearer ${token}`, "User-Agent": USER_AGENT },
    });
    for (const child of data.data?.children || []) {
      const post = child.data;
      threads.push({
        title: post.title,
        created: post.created_utc * 1000,
        comments: post.num_comments,
        score: post.score,
      });
    }
    after = data.data?.after;
    if (!after) break;
  }
  return threads;
}

// Word-boundary match so "Nets" does not match "Hornets".
const matchesTeam = (title, team) => {
  const escaped = String(team.nick || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return Boolean(escaped) && new RegExp(`\\b${escaped}\\b`, "i").test(title);
};

// Only counts are kept; thread text is never stored (it is full of spoilers).
export function matchThreads(threads, game) {
  const start = new Date(game.date).getTime();
  const result = {};
  for (const thread of threads) {
    if (thread.created < start - 4 * 60 * 60 * 1000 || thread.created > start + THREAD_WINDOW_MS) continue;
    if (!matchesTeam(thread.title, game.home) || !matchesTeam(thread.title, game.away)) continue;
    const kind = /post[\s-]*game/i.test(thread.title) ? "post" : /game thread/i.test(thread.title) ? "live" : null;
    if (!kind) continue;
    const existing = result[kind];
    if (!existing || thread.comments > existing.comments) {
      result[kind] = { comments: thread.comments, score: thread.score };
    }
  }
  return Object.keys(result).length ? result : null;
}
