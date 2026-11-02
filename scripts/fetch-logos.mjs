// Downloads each team logo once into docs/logos/<ABBR>.png so the site serves its own copies
// instead of hotlinking ESPN's CDN. Existing files are never refetched.
// Usage: node scripts/fetch-logos.mjs [--force]
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, fetchJson, parseArgs, sleep } from "./lib/util.mjs";

const SIZE = 96;
const LOGO_DIR = join(ROOT, "docs", "logos");
const force = Boolean(parseArgs(process.argv.slice(2)).force);

const data = await fetchJson("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams");
const teams = data.sports?.[0]?.leagues?.[0]?.teams?.map((t) => t.team) || [];
if (teams.length < 30) throw new Error(`Expected 30 teams, got ${teams.length}`);

mkdirSync(LOGO_DIR, { recursive: true });
let fetched = 0;
for (const team of teams) {
  const file = join(LOGO_DIR, `${team.abbreviation}.png`);
  if (existsSync(file) && !force) continue;
  const source = team.logos?.[0]?.href;
  if (!source) continue;
  const path = new URL(source).pathname;
  const response = await fetch(`https://a.espncdn.com/combiner/i?img=${path}&w=${SIZE}&h=${SIZE}`, { signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`Logo ${team.abbreviation}: HTTP ${response.status}`);
  writeFileSync(file, Buffer.from(await response.arrayBuffer()));
  fetched += 1;
  await sleep(200);
}
console.log(`logos: ${fetched} downloaded, ${teams.length - fetched} already present`);
