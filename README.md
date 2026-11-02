# NBAWatch

A static dashboard that scores every NBA game on how worth watching it is. A scheduled GitHub Action collects the data into JSON files; the site in `docs/` just reads them, so there are no API keys or rate limits in the browser.

## How it works

```
GitHub Action (every 3 hours)
  scripts/update.mjs   fetch ESPN, api-sports, Reddit  ->  data/<source>/<season>.json
  scripts/build.mjs    merge + score                   ->  docs/data/<season>.json, index.json
docs/                  static dashboard (GitHub Pages) reads docs/data/
```

| Source | Used for | Needs |
| --- | --- | --- |
| ESPN (public JSON) | Schedule, box scores, play-by-play, win probability, top performers. Primary source. | Nothing |
| api-sports.io | Extra stats ESPN lacks (longest run, second-chance points) and a fallback if ESPN is missing a game. The free plan only covers older seasons and 100 calls/day, so the script spends a small per-run budget. | `NBAWATCH_API_KEY` |
| Reddit (r/nba) | Game-thread and post-game-thread comment counts as a "buzz" signal. Only counts are stored, never thread text. | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |

Sources that have no credentials are skipped, so ESPN alone is enough to run everything.

## Rewatch score (0-100)

- **Box score (35%)**: total scoring, shooting, threes, assists, steals and blocks, star performances (high individual scoring, triple-doubles) and a penalty for turnovers.
- **Game flow (45%)**: final margin, margin entering the last five minutes, lead changes, overtime, size of comeback, and how long win probability stayed near 50/50.
- **Fan buzz (20%)**: r/nba comment volume as a percentile within the season. When Reddit data is missing, the other two parts are re-weighted.

Tiers (Must watch / Worth it / Fine / Skip) are percentiles within the selected season. The weights and thresholds live in [`scripts/lib/score.mjs`](scripts/lib/score.mjs); after changing them run `npm run build` to rescore everything from the stored data without any network calls.

The dashboard blurs scores, stat lines and top performers by default; click a blurred value to reveal it.

## Setup

1. Push this repo to GitHub and enable Pages: **Settings > Pages > Deploy from a branch > `main` / `/docs`**.
2. Optional secrets (**Settings > Secrets and variables > Actions**): `NBAWATCH_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`. For Reddit, create a "script" app at <https://www.reddit.com/prefs/apps> (read-only access is enough).
3. Run the **Update data** workflow once. For a back catalog, use *Run workflow* with `from` set to a start day (for example `2025-10-01`) and `sources` set to `espn`. The job commits its progress even if it times out, so you can run it again to continue; finished games are never refetched.

## Local use

Requires Node 22.9+ (no dependencies).

```bash
npm test                                       # unit tests
node scripts/update.mjs --days 3               # refresh the last 3 days, then rebuild
node scripts/update.mjs --from 2025-10-01 --sources espn   # backfill
npm run build                                  # rescore from stored data
cd docs && python3 -m http.server 8000         # or any static server, then open http://localhost:8000
```

Options for `update.mjs`: `--from`, `--to`, `--days`, `--sources espn,apisports,reddit`, `--concurrency`, `--apisports-budget`, `--no-build`. A `.env` file with the secrets above is picked up by `npm run update`.

`scripts/import-sqlite.mjs` was a one-off import of the old desktop app's `nba_cache.sqlite` into `data/apisports/`.

## Notes

- ESPN's endpoints are unofficial and could change; the raw play-by-play is reduced to a few numbers at fetch time, so parsers are the only thing to update if that happens.
- Reddit's search only reaches back about a week, so buzz is only available for recent games.
- Games are grouped by US Eastern date.
