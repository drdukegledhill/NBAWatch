import sys
import requests
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit

API_KEY = "e4369477d21248708eb56aaaab3697b7"  # User's API key
BASE_URL = "https://v2.nba.api-sports.io/teams"

class NBAApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NBA Teams Viewer")
        self.setGeometry(100, 100, 400, 500)
        self.layout = QVBoxLayout()

        self.button = QPushButton("Fetch NBA Teams")
        self.button.clicked.connect(self.fetch_teams)
        self.layout.addWidget(self.button)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.layout.addWidget(self.text_area)

        self.setLayout(self.layout)

    def fetch_teams(self):
        headers = {"x-apisports-key": API_KEY}
        response = requests.get(BASE_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            teams = [f"{team['name']} (ID: {team['id']})" for team in data.get("response", [])]
            self.text_area.setText("\n".join(teams))
        else:
            self.text_area.setText(f"Error: {response.status_code}\n{response.text}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NBAApp()
    window.show()
    sys.exit(app.exec_()) 