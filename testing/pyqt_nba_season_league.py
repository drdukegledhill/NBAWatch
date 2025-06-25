import sys
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox
)

API_KEY = "e4369477d21248708eb56aaaab3697b7"
SEASONS = [str(year) for year in range(2010, 2025)]  # Example seasons

class NBASeasonLeagueApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NBA Season & League Selector")
        self.setGeometry(100, 100, 400, 200)
        self.layout = QVBoxLayout()

        self.season_label = QLabel("Select Season:")
        self.layout.addWidget(self.season_label)

        self.season_combo = QComboBox()
        self.season_combo.addItems(SEASONS)
        self.layout.addWidget(self.season_combo)

        self.league_label = QLabel("Select League:")
        self.layout.addWidget(self.league_label)

        self.league_combo = QComboBox()
        self.layout.addWidget(self.league_combo)

        self.fetch_leagues_btn = QPushButton("Fetch Leagues")
        self.fetch_leagues_btn.clicked.connect(self.fetch_leagues)
        self.layout.addWidget(self.fetch_leagues_btn)

        self.setLayout(self.layout)

    def fetch_leagues(self):
        season = self.season_combo.currentText()
        url = f"https://v2.nba.api-sports.io/leagues?season={season}"
        headers = {"x-apisports-key": API_KEY}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                self.league_combo.clear()
                leagues = data.get("response", [])
                for league in leagues:
                    name = league.get("name", "Unknown League")
                    league_id = league.get("id", "")
                    self.league_combo.addItem(f"{name} (ID: {league_id})", league_id)
                if not leagues:
                    self.league_combo.addItem("No leagues found", "")
            else:
                QMessageBox.warning(self, "API Error", f"Error: {response.status_code}\n{response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NBASeasonLeagueApp()
    window.show()
    sys.exit(app.exec_()) 