import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox
)

API_KEY = "e4369477d21248708eb56aaaab3697b7"
SEASONS = [str(year) for year in range(2010, 2025)]  # Example seasons

class NBASeasonGameApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NBA Season & Game Selector")
        self.setGeometry(100, 100, 500, 300)
        self.layout = QVBoxLayout()

        self.season_label = QLabel("Select Season:")
        self.layout.addWidget(self.season_label)

        self.season_combo = QComboBox()
        self.season_combo.addItems(SEASONS)
        self.layout.addWidget(self.season_combo)

        self.game_label = QLabel("Select Game:")
        self.layout.addWidget(self.game_label)

        self.game_combo = QComboBox()
        self.layout.addWidget(self.game_combo)

        self.fetch_games_btn = QPushButton("Fetch Games")
        self.fetch_games_btn.clicked.connect(self.fetch_games)
        self.layout.addWidget(self.fetch_games_btn)

        self.setLayout(self.layout)

    def fetch_games(self):
        season = self.season_combo.currentText()
        url = f"https://v2.nba.api-sports.io/games?season={season}"
        headers = {"x-apisports-key": API_KEY}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.game_combo.clear()
                games = data.get("response", [])
                for game in games:
                    home = game["teams"]["home"]["name"]
                    away = game["teams"]["away"]["name"]
                    date = game["date"][:10]  # YYYY-MM-DD
                    game_id = game["id"]
                    self.game_combo.addItem(f"{date}: {away} @ {home}", game_id)
                if not games:
                    self.game_combo.addItem("No games found", "")
            else:
                QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NBASeasonGameApp()
    window.show()
    sys.exit(app.exec_()) 