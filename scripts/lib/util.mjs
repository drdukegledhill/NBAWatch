import { mkdirSync, readFileSync, renameSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const DATA_DIR = join(ROOT, "data");
export const OUT_DIR = join(ROOT, "docs", "data");

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function readJson(path, fallback) {
  if (!existsSync(path)) return fallback;
  return JSON.parse(readFileSync(path, "utf8"));
}

// One entry per line (two levels deep) so git diffs of the data files stay readable.
export function stringifyLines(obj) {
  const lines = Object.entries(obj).map(([key, value]) => {
    if (Array.isArray(value) && value.length && typeof value[0] === "object") {
      return `${JSON.stringify(key)}:[\n${value.map((item) => JSON.stringify(item)).join(",\n")}\n]`;
    }
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const inner = Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}:${JSON.stringify(v)}`);
      return `${JSON.stringify(key)}:{\n${inner.join(",\n")}\n}`;
    }
    return `${JSON.stringify(key)}:${JSON.stringify(value)}`;
  });
  return `{\n${lines.join(",\n")}\n}\n`;
}

export function writeJson(path, obj) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, stringifyLines(obj));
  renameSync(tmp, path);
}

export async function fetchJson(url, { headers = {}, retries = 3, timeoutMs = 30000, method = "GET", body } = {}) {
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      const response = await fetch(url, { headers, method, body, signal: AbortSignal.timeout(timeoutMs) });
      if (response.status === 429 || response.status >= 500) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.ok) {
        const error = new Error(`HTTP ${response.status} for ${url}`);
        error.fatal = true;
        throw error;
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      if (error.fatal || attempt === retries) break;
      await sleep(1000 * 2 ** attempt);
    }
  }
  throw lastError;
}

export async function mapPool(items, concurrency, worker) {
  const results = new Array(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      results[index] = await worker(items[index], index);
    }
  });
  await Promise.all(runners);
  return results;
}

const etFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

// NBA "game day" is the US Eastern date, so late games don't roll into the next UTC day.
export function etDay(isoOrDate) {
  return etFormatter.format(new Date(isoOrDate));
}

export function addDays(day, delta) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(from, to) {
  const days = [];
  for (let day = from; day <= to; day = addDays(day, 1)) days.push(day);
  return days;
}

// Season key is the start year: Oct 2024 - Jun 2025 is "2024".
export function seasonKey(day) {
  const [year, month] = day.split("-").map(Number);
  return String(month >= 8 ? year : year - 1);
}

export function seasonLabel(key) {
  const start = Number(key);
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

export const nick = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");

export const gameKey = (day, homeNick, awayNick) => `${day}|${nick(homeNick)}|${nick(awayNick)}`;

export function num(value) {
  if (value === null || value === undefined || value === "" || value === "-") return null;
  const parsed = Number.parseFloat(String(value).replace("%", ""));
  return Number.isFinite(parsed) ? parsed : null;
}

export function storePath(source, season) {
  return join(DATA_DIR, source, `${season}.json`);
}

export function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}
