import sys
print("Python executable:", sys.executable)
import requests
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

        # Add Quit button at the bottom right
        self.quit_row = QHBoxLayout()
        self.quit_row.addStretch()
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.clicked.connect(QApplication.instance().quit)
        self.quit_row.addWidget(self.quit_btn)
        self.layout.addLayout(self.quit_row)

        self.setLayout(self.layout)

    def fetch_games(self):
        season = self.season_combo.currentText()
        url = f"https://v2.nba.api-sports.io/games?season={season}"
        headers = {"x-apisports-key": API_KEY}
        try:
            response = requests.get(url, headers=headers)
            print("Status:", response.status_code)
            print("URL:", url)
            print("Raw response:", response.text[:1000])  # For debugging
            if response.status_code == 200:
                data = response.json()
                self.game_combo.clear()
                games = data.get("response", [])
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
            else:
                QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def fetch_game_stats(self):
        idx = self.game_combo.currentIndex()
        if idx == -1:
            QMessageBox.warning(self, "No Game Selected", "Please select a game.")
            return
        game_id = self.game_combo.itemData(idx)
        if not game_id:
            QMessageBox.warning(self, "No Game Selected", "Please select a valid game.")
            return
        url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
        headers = {"x-apisports-key": API_KEY}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                stats = data.get("response", [])
                if len(stats) != 2:
                    QMessageBox.warning(self, "Stats Error", "Could not retrieve stats for both teams.")
                    return
                self.display_team_info(stats)
                self.display_stats_table(stats)
            else:
                QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NBAWatchApp()
    window.show()
    sys.exit(app.exec_()) 