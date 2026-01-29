import sys
print("Python executable:", sys.executable)
import requests
import os
import json
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from io import BytesIO

API_KEY = "e4369477d21248708eb56aaaab3697b7"  # User's API key
SEASONS = ["2021", "2022", "2023"]  # Only allowed seasons for free plan

class NBAWatchApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NBAWatch: Season & Game Selector")
        self.setGeometry(100, 100, 900, 600)
        self.layout = QVBoxLayout()

        # Horizontal layout for season selection and button
        self.season_row = QHBoxLayout()
        self.season_label = QLabel("Select Season:")
        self.season_row.addWidget(self.season_label)

        self.season_combo = QComboBox()
        self.season_combo.addItems(SEASONS)
        self.season_row.addWidget(self.season_combo)


        self.get_games_btn = QPushButton("Get Games")
        self.get_games_btn.clicked.connect(self.fetch_games)
        self.season_row.addWidget(self.get_games_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Force refresh games list for selected season")
        self.refresh_btn.clicked.connect(lambda: self.fetch_games(force_refresh=True))
        self.season_row.addWidget(self.refresh_btn)

        self.layout.addLayout(self.season_row)

        self.game_label = QLabel("Select Game:")
        self.layout.addWidget(self.game_label)

        self.game_combo = QComboBox()
        self.layout.addWidget(self.game_combo)

        self.get_stats_btn = QPushButton("Get Game Stats")
        self.get_stats_btn.clicked.connect(self.fetch_game_stats)
        self.layout.addWidget(self.get_stats_btn)

        # Team info and stats table
        self.teams_row = QHBoxLayout()
        self.team1_box = QVBoxLayout()
        self.team2_box = QVBoxLayout()
        self.teams_row.addLayout(self.team1_box)
        self.teams_row.addLayout(self.team2_box)
        self.layout.addLayout(self.teams_row)

        self.stats_table = QTableWidget()
        self.layout.addWidget(self.stats_table)

        # Add Rewatch Score label
        self.rewatch_label = QLabel("Rewatch Score: N/A")
        self.rewatch_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px 0;")
        self.layout.addWidget(self.rewatch_label)

        # Add Quit button at the bottom right
        self.quit_row = QHBoxLayout()
        self.quit_row.addStretch()
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.clicked.connect(QApplication.instance().quit)
        self.quit_row.addWidget(self.quit_btn)
        self.layout.addLayout(self.quit_row)

        self.setLayout(self.layout)

    def fetch_games(self, force_refresh=False):
        season = self.season_combo.currentText()
        cache_file = f"nba_games_{season}.json"
        games_data = None
        # Try to load from cache unless force_refresh
        if not force_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    games_data = data.get("response", [])
                    print(f"Loaded games for season {season} from cache.")
            except Exception as e:
                print("Cache load error:", e)
                games_data = None
        if games_data is None:
            url = f"https://v2.nba.api-sports.io/games?season={season}"
            headers = {"x-apisports-key": API_KEY}
            try:
                response = requests.get(url, headers=headers)
                print("Status:", response.status_code)
                print("URL:", url)
                print("Raw response:", response.text[:1000])  # For debugging
                if response.status_code == 200:
                    data = response.json()
                    games_data = data.get("response", [])
                    # Save to cache
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                        print(f"Saved games for season {season} to cache.")
                    except Exception as e:
                        print("Cache save error:", e)
                else:
                    QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
                return
        self.game_combo.clear()
        games = games_data
        added = False
        for game in games:
            try:
                home = game["teams"]["home"]["name"]
                away = game["teams"]["visitors"]["name"]
                date = game["date"]["start"][:10] if isinstance(game["date"], dict) else game["date"][:10]
                game_id = game["id"]
                self.game_combo.addItem(f"{date}: {away} @ {home}", game_id)
                added = True
            except Exception as e:
                print("Error parsing game:", e)
                continue  # Skip games with missing data
        if not added:
            self.game_combo.addItem("No games found", "")

    def fetch_game_stats(self, force_refresh=False):
        idx = self.game_combo.currentIndex()
        if idx == -1:
            QMessageBox.warning(self, "No Game Selected", "Please select a game.")
            return
        game_id = self.game_combo.itemData(idx)
        if not game_id:
            QMessageBox.warning(self, "No Game Selected", "Please select a valid game.")
            return
        cache_file = f"nba_game_stats_{game_id}.json"
        stats_data = None
        # Try to load from cache unless force_refresh
        if not force_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    stats_data = data.get("response", [])
                    print(f"Loaded stats for game {game_id} from cache.")
            except Exception as e:
                print("Stats cache load error:", e)
                stats_data = None
        if stats_data is None:
            url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
            headers = {"x-apisports-key": API_KEY}
            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    stats_data = data.get("response", [])
                    # Save to cache
                    try:
                        with open(cache_file, "w", encoding="utf-8") as f:
                            json.dump(data, f)
                        print(f"Saved stats for game {game_id} to cache.")
                    except Exception as e:
                        print("Stats cache save error:", e)
                else:
                    QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
                    return
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
                return
        stats = stats_data
        if len(stats) != 2:
            QMessageBox.warning(self, "Stats Error", "Could not retrieve stats for both teams.")
            return
        self.display_team_info(stats)
        self.display_stats_table(stats)

    def display_team_info(self, stats):
        # Clear previous
        for i in reversed(range(self.team1_box.count())):
            widget = self.team1_box.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        for i in reversed(range(self.team2_box.count())):
            widget = self.team2_box.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        # Team 1
        team1 = stats[0]["team"]
        name1 = QLabel(team1.get("name", ""))
        logo1 = QLabel()
        self.set_logo_pixmap(logo1, team1.get("logo"))
        self.team1_box.addWidget(name1)
        self.team1_box.addWidget(logo1)
        # Team 2
        team2 = stats[1]["team"]
        name2 = QLabel(team2.get("name", ""))
        logo2 = QLabel()
        self.set_logo_pixmap(logo2, team2.get("logo"))
        self.team2_box.addWidget(name2)
        self.team2_box.addWidget(logo2)

    def set_logo_pixmap(self, label, url):
        if url:
            try:
                print("Loading logo from:", url)
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    img_data = response.content
                    pixmap = QPixmap()
                    if pixmap.loadFromData(img_data) and not pixmap.isNull():
                        pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        label.setPixmap(pixmap)
                    else:
                        label.setText("[No Logo]")
                else:
                    label.setText("[No Logo]")
            except Exception as e:
                print("Logo load error:", e)
                label.setText("[No Logo]")
        else:
            label.setText("[No Logo]")

    STAT_MEANINGS = {
        "fastBreakPoints": "Fast Break Points",
        "pointsInPaint": "Points in Paint",
        "biggestLead": "Biggest Lead",
        "secondChancePoints": "Second Chance Points",
        "pointsOffTurnovers": "Points Off Turnovers",
        "longestRun": "Longest Run",
        "points": "Points",
        "fgm": "Field Goals Made",
        "fga": "Field Goals Attempted",
        "fgp": "Field Goal Percentage",
        "ftm": "Free Throws Made",
        "fta": "Free Throws Attempted",
        "ftp": "Free Throw Percentage",
        "tpm": "Three-Point Field Goals Made",
        "tpa": "Three-Point Field Goals Attempted",
        "tpp": "Three-Point Percentage",
        "offReb": "Offensive Rebounds",
        "defReb": "Defensive Rebounds",
        "totReb": "Total Rebounds",
        "assists": "Assists",
        "pFouls": "Personal Fouls",
        "steals": "Steals",
        "turnovers": "Turnovers",
        "blocks": "Blocks",
        "plusMinus": "+/-",
        "min": "Minutes Played"
    }

    def display_stats_table(self, stats):
        stat_dicts = []
        for team_stats in stats:
            statistics = team_stats["statistics"]
            if isinstance(statistics, list):
                if statistics and isinstance(statistics[0], dict) and "type" not in statistics[0]:
                    stat_dict = statistics[0]
                else:
                    stat_dict = {}
                    for item in statistics:
                        if isinstance(item, dict) and "type" in item and "value" in item:
                            stat_dict[item["type"]] = item["value"]
                stat_dicts.append(stat_dict)
            else:
                stat_dicts.append(statistics)

        # Collect all stat keys
        stat_keys = set()
        for stat_dict in stat_dicts:
            stat_keys.update(stat_dict.keys())
        stat_keys = sorted(stat_keys)

        self.stats_table.clear()
        self.stats_table.setRowCount(len(stat_keys))
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(["Stat", stats[0]["team"]["name"], stats[1]["team"]["name"]])

        for row, key in enumerate(stat_keys):
            stat_name = self.STAT_MEANINGS.get(key, key)
            self.stats_table.setItem(row, 0, QTableWidgetItem(stat_name))
            val1 = stat_dicts[0].get(key, "-")
            val2 = stat_dicts[1].get(key, "-")
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(val1)))
            self.stats_table.setItem(row, 2, QTableWidgetItem(str(val2)))
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # Calculate and display rewatch score
        self.display_rewatch_score(stat_dicts)

    def display_rewatch_score(self, stat_dicts):
        # Helper to safely get float values
        def get_float(d, key):
            try:
                val = d.get(key, 0)
                if val is None or val == "-":
                    return 0.0
                return float(str(val).replace("%", ""))
            except Exception:
                return 0.0

        t1, t2 = stat_dicts
        # Offensive
        points = get_float(t1, "points") + get_float(t2, "points")
        assists = get_float(t1, "assists") + get_float(t2, "assists")
        fg_pct = (get_float(t1, "fgp") + get_float(t2, "fgp")) / 2
        tp_pct = (get_float(t1, "tpp") + get_float(t2, "tpp")) / 2
        tpm = get_float(t1, "tpm") + get_float(t2, "tpm")
        # Defensive
        steals = get_float(t1, "steals") + get_float(t2, "steals")
        blocks = get_float(t1, "blocks") + get_float(t2, "blocks")
        # Chaos
        close_game = max(0, 10 - abs(get_float(t1, "points") - get_float(t2, "points"))) * 2
        turnovers = get_float(t1, "turnovers") + get_float(t2, "turnovers")
        # Hot hand
        hot_hand = 5 if get_float(t1, "fgp") > 70 or get_float(t2, "fgp") > 70 else 0

        rewatch_score = 0
        rewatch_score += points / 20
        rewatch_score += assists / 8
        rewatch_score += fg_pct / 2
        rewatch_score += tp_pct / 2
        rewatch_score += tpm / 4
        rewatch_score += steals / 4
        rewatch_score += blocks / 4
        rewatch_score += close_game
        rewatch_score -= turnovers / 2
        rewatch_score += hot_hand
        rewatch_score = min(100, rewatch_score)

        print(
            "points:",
            points,
            "assists:",
            assists,
            "fg_pct:",
            fg_pct,
            "tp_pct:",
            tp_pct,
            "tpm:",
            tpm,
            "steals:",
            steals,
            "blocks:",
            blocks,
            "close_game:",
            close_game,
            "turnovers:",
            turnovers,
            "hot_hand:",
            hot_hand,
        )

        self.rewatch_label.setText(f"Rewatch Score: {rewatch_score:.1f}")

    def preload_all_stats(self):
        season = self.season_combo.currentText()
        cache_file = f"nba_games_{season}.json"
        if not os.path.exists(cache_file):
            QMessageBox.warning(self, "No Games Cached", "Please fetch games for this season first.")
            return
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            games = data.get("response", [])
        total = len(games)
        done = 0
        for game in games:
            try:
                game_id = game["id"]
                stats_cache = f"nba_game_stats_{game_id}.json"
                if not os.path.exists(stats_cache):
                    url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
                    headers = {"x-apisports-key": API_KEY}
                    response = requests.get(url, headers=headers)
                    if response.status_code == 200:
                        with open(stats_cache, "w", encoding="utf-8") as sf:
                            sf.write(response.text)
                        done += 1
                else:
                    done += 1
            except Exception as e:
                print(f"Error caching stats for game {game.get('id', '?')}: {e}")
        QMessageBox.information(self, "Preload Complete", f"Stats cached for {done}/{total} games in {season}.")

    def process_whole_year(self):
        season = self.season_combo.currentText()
        cache_file = f"nba_games_{season}.json"
        if not os.path.exists(cache_file):
            QMessageBox.warning(self, "No Games Cached", "Please fetch games for this season first.")
            return
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            games = data.get("response", [])
        results = []
        for game in games:
            game_id = game["id"]
            stats_cache = f"nba_game_stats_{game_id}.json"
            if not os.path.exists(stats_cache):
                continue
            try:
                with open(stats_cache, "r", encoding="utf-8") as sf:
                    stats_data = json.load(sf)
                    stats = stats_data.get("response", [])
                if len(stats) != 2:
                    continue
                # Calculate rewatch score using the same logic as display_rewatch_score
                def get_float(d, key):
                    try:
                        val = d.get(key, 0)
                        if val is None or val == "-":
                            return 0.0
                        return float(str(val).replace("%", ""))
                    except Exception:
                        return 0.0

                stat_dicts = []
                for team_stats in stats:
                    statistics = team_stats["statistics"]
                    if isinstance(statistics, list):
                        if statistics and isinstance(statistics[0], dict) and "type" not in statistics[0]:
                            stat_dict = statistics[0]
                        else:
                            stat_dict = {}
                            for item in statistics:
                                if isinstance(item, dict) and "type" in item and "value" in item:
                                    stat_dict[item["type"]] = item["value"]
                        stat_dicts.append(stat_dict)
                    else:
                        stat_dicts.append(statistics)
                t1, t2 = stat_dicts
                points = get_float(t1, "points") + get_float(t2, "points")
                assists = get_float(t1, "assists") + get_float(t2, "assists")
                fg_pct = (get_float(t1, "fgp") + get_float(t2, "fgp")) / 2
                tp_pct = (get_float(t1, "tpp") + get_float(t2, "tpp")) / 2
                tpm = get_float(t1, "tpm") + get_float(t2, "tpm")
                steals = get_float(t1, "steals") + get_float(t2, "steals")
                blocks = get_float(t1, "blocks") + get_float(t2, "blocks")
                close_game = max(0, 10 - abs(get_float(t1, "points") - get_float(t2, "points"))) * 2
                turnovers = get_float(t1, "turnovers") + get_float(t2, "turnovers")
                hot_hand = 5 if get_float(t1, "fgp") > 70 or get_float(t2, "fgp") > 70 else 0
                rewatch_score = 0
                rewatch_score += points / 20
                rewatch_score += assists / 8
                rewatch_score += fg_pct / 2
                rewatch_score += tp_pct / 2
                rewatch_score += tpm / 4
                rewatch_score += steals / 4
                rewatch_score += blocks / 4
                rewatch_score += close_game
                rewatch_score -= turnovers / 2
                rewatch_score += hot_hand
                rewatch_score = min(100, rewatch_score)
                # Compose display info
                home = game["teams"]["home"]["name"]
                away = game["teams"]["visitors"]["name"]
                date = game["date"]["start"][:10] if isinstance(game["date"], dict) else game["date"][:10]
                results.append(
                    {"game_id": game_id, "desc": f"{date}: {away} @ {home}", "rewatch_score": rewatch_score}
                )
            except Exception as e:
                print(f"Error processing game {game_id}: {e}")
        # Sort by rewatch score descending
        results.sort(key=lambda x: x["rewatch_score"], reverse=True)
        # Show in table
        self.show_year_table(results)

    def show_year_table(self, results):
        # Remove old table if exists
        if hasattr(self, "year_table"):
            self.layout.removeWidget(self.year_table)
            self.year_table.deleteLater()
            del self.year_table
        self.year_table = QTableWidget()
        self.year_table.setRowCount(len(results))
        self.year_table.setColumnCount(3)
        self.year_table.setHorizontalHeaderLabels(["Game", "Rewatch Score", "View"])
        for row, item in enumerate(results):
            self.year_table.setItem(row, 0, QTableWidgetItem(item["desc"]))
            self.year_table.setItem(row, 1, QTableWidgetItem(f"{item['rewatch_score']:.1f}"))
            btn = QPushButton("View")
            btn.clicked.connect(lambda _, gid=item["game_id"]: self.goto_game(gid))
            self.year_table.setCellWidget(row, 2, btn)
        self.year_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.year_table)

    def goto_game(self, game_id):
        # Find and select the game in the combo box, then fetch stats
        idx = -1
        for i in range(self.game_combo.count()):
            if self.game_combo.itemData(i) == game_id:
                idx = i
                break
        if idx != -1:
            self.game_combo.setCurrentIndex(idx)
            self.fetch_game_stats()
        else:
            QMessageBox.warning(self, "Game Not Found", "Game not found in combo box. Try refreshing games list.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NBAWatchApp()
    window.show()
    sys.exit(app.exec_()) 
