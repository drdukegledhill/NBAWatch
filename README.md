# NBAWatch

NBAWatch is a browser-based app for exploring NBA games, comparing team stats, and finding the most rewatchable matchups.

## Features

- Browse games for the available seasons (2022–2024).
- View team stats, logos, and a rewatch score for each game.
- Cache season stats with progress controls and build season rankings.
- Store the API key and cached responses in the browser.

## Getting started

1. Open `docs/index.html` in a browser, or publish the contents of `docs/` using any static web host.
2. Get an API key from [API-Sports](https://dashboard.api-sports.io/), enter it in the **API Key** field, and click **Save**.
3. Choose a season and use **Get Games**, **Get Game Stats**, or **Build Season Rewatch Rankings**.

NBAWatch is a static web app: it has no build step or server-side component. A static HTTP server or host is recommended if your browser restricts requests from locally opened files.

## Data and privacy

The app sends requests directly from your browser to the NBA API. Your API key is saved in browser `localStorage`, and game/stat responses are cached there for up to seven days. The key is available to anyone who can use that browser profile, so use an API key you are comfortable using client-side. Select **Clear Local Cache** to remove NBAWatch's saved key and cached data from that browser.

## Rewatch score

The 0–100 rewatch score combines scoring, assists, shooting, three-pointers, steals, blocks, game closeness, turnovers, and a bonus for exceptional field-goal accuracy. High-scoring, close games with strong shooting and defensive highlights tend to score higher.

## Troubleshooting

- **API key missing:** Enter your API key and click **Save**.
- **Rate limit or empty results:** Check your API-Sports plan and quota, then retry after the limit resets.
- **Stats unavailable:** Some games may not have stats yet; try again later.
