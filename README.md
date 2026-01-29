# NBAWatch

NBAWatch is a desktop application for exploring NBA game data, built with Python and PyQt5. It allows you to:
- Select a season and browse all NBA games for that year
- View detailed team stats and logos for any game
- Instantly see a "rewatch score" that estimates how entertaining a game is to rewatch, based on real stats

## Features
- **Season and Game Selection:** Choose from available NBA seasons (2021–2023 for free API plans) and select any game.
- **Team Logos and Stats:** View both teams' names, logos, and a full table of game stats.
- **Rewatch Score:** Get a single number (0–100) summarizing the game's entertainment value, calculated from offensive, defensive, and dramatic factors.
- **Modern UI:** Built with PyQt5 for a responsive, cross-platform desktop experience.
- **Local Caching:** Game lists and stats are cached locally to reduce API calls and speed up repeat usage.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/drdukegledhill/NBAWatch.git
   cd NBAWatch
   ```
2. **Install dependencies:**
   ```bash
   pip3 install -r requirements.txt
   # Or, at minimum:
   pip3 install PyQt5 requests
   ```
3. **API Key:**
   - Get a free API key from [api-sports.io](https://dashboard.api-sports.io/)
   - Insert your key in `NBAWatch.py` at the line:
     ```python
     API_KEY = "YOUR_API_KEY"
     ```
4. **Run the app:**
   ```bash
   python3 testing/NBAWatch.py
   ```

## Caching

API responses are cached in `testing/` as `nba_games_*.json` and `nba_game_stats_*.json` to speed up repeat usage. These files are ignored by git.

## Rewatch Score Calculation

The rewatch score is a single number (0–100) that estimates how entertaining a basketball game is to rewatch, based on a mix of offensive, defensive, and dramatic factors:

### How the Score is Calculated

- **Offensive Appeal**
  - Total Points: More points = more action
  - Assists: More assists = better ball movement
  - Field Goal %: Higher accuracy = more made shots
  - Three-Point %: Higher accuracy = more exciting long-range shots
  - Three-Pointers Made: More = more spectacular plays
- **Defensive Highlights**
  - Steals: More = more fast breaks and defensive excitement
  - Blocks: More = more dramatic defensive plays
- **Chaos Factor**
  - Close Game Bonus: The closer the final score, the higher the bonus (up to a maximum)
  - Turnovers Penalty: More turnovers = sloppier play, which reduces the score
- **Hot Hand Bonus**
  - If either team shoots over 70% from the field, add a bonus for "hot hand" performances
- **Final Step**
  - All these components are combined (with each factor scaled to keep the score reasonable), and the total is capped at 100.

## Example
A game with lots of points, assists, accurate shooting, exciting 3-pointers, defensive highlights, and a close finish will have a high rewatch score. Games with lots of turnovers or a blowout score will have a lower score. 
