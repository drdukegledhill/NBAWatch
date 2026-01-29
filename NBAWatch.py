import sys
print("Python executable:", sys.executable)
import requests
import json
import time
import sqlite3
from collections import deque
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QProgressDialog, QProgressBar
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal
from io import BytesIO

API_KEY = "e4369477d21248708eb56aaaab3697b7"  # User's API key
SEASONS = ["2021", "2022", "2023"]  # Only allowed seasons for free plan
DB_PATH = "nba_cache.sqlite"


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def db_init():
    conn = db_connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                season TEXT PRIMARY KEY,
                json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                game_id INTEGER PRIMARY KEY,
                json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def db_get_games(conn, season):
    cur = conn.execute("SELECT json FROM games WHERE season = ?", (season,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def db_save_games(conn, season, data):
    payload = json.dumps(data)
    conn.execute(
        "INSERT OR REPLACE INTO games (season, json, updated_at) VALUES (?, ?, ?)",
        (season, payload, int(time.time())),
    )
    conn.commit()


def db_get_stats(conn, game_id):
    cur = conn.execute("SELECT json FROM stats WHERE game_id = ?", (game_id,))
    row = cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def db_get_valid_games(conn, season):
    data = db_get_games(conn, season)
    if not data:
        return None
    errors = data.get("errors") or {}
    resp = data.get("response")
    if errors:
        db_delete_games(conn, season)
        return None
    if isinstance(resp, list) and len(resp) > 0:
        return data
    db_delete_games(conn, season)
    return None


def db_get_valid_stats(conn, game_id):
    data = db_get_stats(conn, game_id)
    if not data:
        return None
    resp = data.get("response")
    if isinstance(resp, list) and len(resp) == 2:
        return data
    db_delete_stats(conn, game_id)
    return None


def db_has_stats(conn, game_id):
    cur = conn.execute("SELECT 1 FROM stats WHERE game_id = ? LIMIT 1", (game_id,))
    return cur.fetchone() is not None


def db_save_stats(conn, game_id, data):
    payload = json.dumps(data)
    conn.execute(
        "INSERT OR REPLACE INTO stats (game_id, json, updated_at) VALUES (?, ?, ?)",
        (game_id, payload, int(time.time())),
    )
    conn.commit()


def db_delete_stats(conn, game_id):
    conn.execute("DELETE FROM stats WHERE game_id = ?", (game_id,))
    conn.commit()


def db_delete_games(conn, season):
    conn.execute("DELETE FROM games WHERE season = ?", (season,))
    conn.commit()


class StatsCacheWorker(QObject):
    progress = pyqtSignal(int, int, str)  # total, done, status
    finished = pyqtSignal()

    def __init__(self, game_ids, season, api_key):
        super().__init__()
        self.game_ids = list(game_ids)
        self.season = season
        self.api_key = api_key
        self._stop = False

    def stop(self):
        self._stop = True

    def _sleep_interruptible(self, seconds):
        step = 0.2
        remaining = float(seconds)
        while remaining > 0 and not self._stop:
            time.sleep(min(step, remaining))
            remaining -= step
        return not self._stop

    def run(self):
        conn = db_connect()
        total = len(self.game_ids)
        if total == 0:
            self.progress.emit(0, 0, f"No games to cache for season {self.season}.")
            self.finished.emit()
            conn.close()
            return

        missing = deque()
        done = 0
        for game_id in self.game_ids:
            if db_get_valid_stats(conn, game_id):
                done += 1
            else:
                missing.append(game_id)

        self.progress.emit(total, done, f"Caching stats for season {self.season}...")
        if not missing:
            self.progress.emit(total, done, f"All stats already cached for season {self.season}.")
            self.finished.emit()
            conn.close()
            return

        headers = {"x-apisports-key": self.api_key}
        backoff = 15
        max_backoff = 300

        while missing and not self._stop:
            game_id = missing[0]
            if db_get_valid_stats(conn, game_id):
                missing.popleft()
                done += 1
                self.progress.emit(total, done, f"Cached {done}/{total} games for {self.season}.")
                continue

            url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
            try:
                response = requests.get(url, headers=headers, timeout=20)
            except Exception as e:
                self.progress.emit(total, done, f"Request error: {e}. Retrying soon...")
                if not self._sleep_interruptible(5):
                    break
                missing.rotate(-1)
                continue

            if response.status_code == 200:
                try:
                    data = response.json()
                    stats = data.get("response", [])
                    if len(stats) != 2:
                        self.progress.emit(
                            total,
                            done,
                            f"Incomplete stats for game {game_id}. Retrying later...",
                        )
                        if not self._sleep_interruptible(10):
                            break
                        missing.rotate(-1)
                        continue
                    db_save_stats(conn, game_id, data)
                    missing.popleft()
                    done += 1
                    backoff = 15
                    self.progress.emit(total, done, f"Cached {done}/{total} games for {self.season}.")
                except Exception as e:
                    self.progress.emit(total, done, f"Cache save error: {e}. Retrying soon...")
                    if not self._sleep_interruptible(5):
                        break
                    missing.rotate(-1)
            elif response.status_code == 429:
                self.progress.emit(total, done, f"Rate limited (429). Retrying in {backoff}s...")
                if not self._sleep_interruptible(backoff):
                    break
                backoff = min(max_backoff, int(backoff * 1.5))
            else:
                self.progress.emit(
                    total,
                    done,
                    f"API error {response.status_code} for game {game_id}. Retrying later...",
                )
                if not self._sleep_interruptible(5):
                    break
                missing.rotate(-1)

        if self._stop:
            self.progress.emit(total, done, "Caching stopped.")
        else:
            self.progress.emit(total, done, f"All stats cached for season {self.season}.")
        self.finished.emit()
        conn.close()

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

        self.api_status = QLabel("API: idle")
        self.layout.addWidget(self.api_status)

        self.cache_status = QLabel("Stats cache: idle")
        self.layout.addWidget(self.cache_status)
        self.cache_progress = QProgressBar()
        self.cache_progress.setMinimum(0)
        self.cache_progress.setValue(0)
        self.layout.addWidget(self.cache_progress)

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
        self.cache_thread = None
        self.cache_worker = None
        self.games_by_id = {}
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop_stats_cache_worker)

    def fetch_games(self, force_refresh=False):
        season = self.season_combo.currentText()
        games_data = None
        self.api_status.setText("API: fetching games...")
        # Try to load from cache unless force_refresh
        if not force_refresh:
            conn = db_connect()
            try:
                data = db_get_valid_games(conn, season)
                if data:
                    games_data = data.get("response", [])
                    print(f"Loaded games for season {season} from cache.")
            except Exception as e:
                print("Cache load error:", e)
                games_data = None
            finally:
                conn.close()
        if games_data is None:
            url = f"https://v2.nba.api-sports.io/games?season={season}"
            headers = {"x-apisports-key": API_KEY}
            try:
                response = requests.get(url, headers=headers, timeout=20)
                print("Status:", response.status_code)
                print("URL:", url)
                print("Raw response:", response.text[:1000])  # For debugging
                if response.status_code == 200:
                    data = response.json()
                    errors = data.get("errors") or {}
                    games_data = data.get("response", [])
                    results = data.get("results")
                    if errors or not games_data:
                        msg = f"No games returned for season {season}."
                        if results is not None:
                            msg += f" Results: {results}."
                        if errors:
                            msg += f" Errors: {errors}"
                        self.api_status.setText(f"API: {msg}")
                        QMessageBox.warning(self, "API Warning", msg)
                        games_data = []
                        # Ensure we don't cache error responses
                        conn = db_connect()
                        try:
                            db_delete_games(conn, season)
                        finally:
                            conn.close()
                        return
                    # Save to cache
                    try:
                        conn = db_connect()
                        try:
                            db_save_games(conn, season, data)
                        finally:
                            conn.close()
                        print(f"Saved games for season {season} to cache.")
                        self.api_status.setText("API: games loaded")
                    except Exception as e:
                        print("Cache save error:", e)
                        self.api_status.setText(f"API: cache save error: {e}")
                else:
                    msg = f"Error: {response.status_code}\n{response.text}"
                    self.api_status.setText(f"API: {msg}")
                    QMessageBox.warning(self, "API Error", msg)
                    return
            except Exception as e:
                self.api_status.setText(f"API: request error: {e}")
                QMessageBox.critical(self, "Error", str(e))
                return
        self.game_combo.clear()
        games = games_data
        self.games_by_id = {g.get("id"): g for g in games if g.get("id")}
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
            self.api_status.setText("API: no games found")
            return

        self.start_stats_cache_worker(games, season)

    def preload_stats_for_season(self, games, season):
        missing = []
        conn = db_connect()
        for game in games:
            game_id = game.get("id")
            if not game_id:
                continue
            if not db_get_valid_stats(conn, game_id):
                missing.append(game_id)
        conn.close()

        if not missing:
            print(f"All stats already cached for season {season}.")
            return

        progress = QProgressDialog(
            f"Caching stats for {season} ({len(missing)} games)...",
            "Cancel",
            0,
            len(missing),
            self,
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        headers = {"x-apisports-key": API_KEY}
        for i, game_id in enumerate(missing, start=1):
            if progress.wasCanceled():
                break
            url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        conn = db_connect()
                        try:
                            db_save_stats(conn, game_id, data)
                        finally:
                            conn.close()
                    except Exception as e:
                        print(f"Stats cache save error for game {game_id}:", e)
                else:
                    print(f"Stats API error for game {game_id}: {response.status_code}")
            except Exception as e:
                print(f"Stats request error for game {game_id}:", e)
            progress.setValue(i)
            QApplication.processEvents()

    def start_stats_cache_worker(self, games, season):
        game_ids = [g.get("id") for g in games if g.get("id")]
        if self.cache_worker is not None:
            self.stop_stats_cache_worker()

        self.cache_worker = StatsCacheWorker(game_ids, season, API_KEY)
        self.cache_thread = QThread()
        self.cache_worker.moveToThread(self.cache_thread)
        self.cache_thread.started.connect(self.cache_worker.run)
        self.cache_worker.progress.connect(self.on_cache_progress)
        self.cache_worker.finished.connect(self.on_cache_finished)
        self.cache_worker.finished.connect(self.cache_thread.quit)
        self.cache_worker.finished.connect(self.cache_worker.deleteLater)
        self.cache_thread.finished.connect(self.cache_thread.deleteLater)
        self.cache_thread.finished.connect(self.on_cache_thread_finished)
        self.cache_thread.start()

    def stop_stats_cache_worker(self):
        if self.cache_worker is None:
            return
        self.cache_worker.stop()
        if self.cache_thread is not None and self.cache_thread.isRunning():
            self.cache_thread.quit()
            self.cache_thread.wait(15000)

    def on_cache_progress(self, total, done, status):
        self.cache_progress.setMaximum(max(total, 1))
        self.cache_progress.setValue(done)
        self.cache_status.setText(f"Stats cache: {status}")

    def on_cache_finished(self):
        self.cache_worker = None
        self.cache_status.setText("Stats cache: idle")

    def on_cache_thread_finished(self):
        self.cache_thread = None

    def closeEvent(self, event):
        self.stop_stats_cache_worker()
        super().closeEvent(event)

    def fetch_game_stats(self, force_refresh=False):
        idx = self.game_combo.currentIndex()
        if idx == -1:
            QMessageBox.warning(self, "No Game Selected", "Please select a game.")
            return
        game_id = self.game_combo.itemData(idx)
        if not game_id:
            QMessageBox.warning(self, "No Game Selected", "Please select a valid game.")
            return
        stats_data = None
        self.api_status.setText(f"API: fetching stats for game {game_id}...")
        # Try to load from cache unless force_refresh
        if not force_refresh:
            conn = db_connect()
            try:
                data = db_get_valid_stats(conn, game_id)
                if data:
                    stats_data = data.get("response", [])
                    print(f"Loaded stats for game {game_id} from cache.")
                    self.api_status.setText("API: stats loaded from cache")
            except Exception as e:
                print("Stats cache load error:", e)
                stats_data = None
            finally:
                conn.close()
        if stats_data is None:
            url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
            headers = {"x-apisports-key": API_KEY}
            try:
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code == 200:
                    data = response.json()
                    stats_data = data.get("response", [])
                    # Save to cache
                    try:
                        conn = db_connect()
                        try:
                            if len(stats_data) == 2:
                                db_save_stats(conn, game_id, data)
                            else:
                                db_delete_stats(conn, game_id)
                        finally:
                            conn.close()
                        print(f"Saved stats for game {game_id} to cache.")
                        self.api_status.setText("API: stats loaded")
                    except Exception as e:
                        print("Stats cache save error:", e)
                        self.api_status.setText(f"API: stats cache save error: {e}")
                else:
                    msg = f"Error: {response.status_code}\n{response.text}"
                    self.api_status.setText(f"API: {msg}")
                    QMessageBox.warning(self, "API Error", msg)
                    return
            except Exception as e:
                self.api_status.setText(f"API: stats request error: {e}")
                QMessageBox.critical(self, "Error", str(e))
                return
        stats = stats_data
        if len(stats) != 2:
            game = self.games_by_id.get(game_id)
            status = None
            if game:
                status = game.get("status", {}).get("long")
            if status and status.lower() != "finished":
                QMessageBox.warning(
                    self,
                    "Stats Not Ready",
                    f"Stats are not available until the game is finished. Status: {status}.",
                )
                self.api_status.setText(f"API: stats not ready (status: {status})")
            else:
                QMessageBox.warning(self, "Stats Error", "Could not retrieve stats for both teams.")
                self.api_status.setText("API: stats incomplete for this game")
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
        conn = db_connect()
        try:
            data = db_get_valid_games(conn, season)
            if not data:
                QMessageBox.warning(self, "No Games Cached", "Please fetch games for this season first.")
                return
            games = data.get("response", [])
        finally:
            conn.close()
        total = len(games)
        done = 0
        for game in games:
            try:
                game_id = game["id"]
                conn = db_connect()
                try:
                    has_stats = db_get_valid_stats(conn, game_id) is not None
                finally:
                    conn.close()
                if not has_stats:
                    url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
                    headers = {"x-apisports-key": API_KEY}
                    response = requests.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        conn = db_connect()
                        try:
                            db_save_stats(conn, game_id, data)
                        finally:
                            conn.close()
                        done += 1
                else:
                    done += 1
            except Exception as e:
                print(f"Error caching stats for game {game.get('id', '?')}: {e}")
        QMessageBox.information(self, "Preload Complete", f"Stats cached for {done}/{total} games in {season}.")

    def process_whole_year(self):
        season = self.season_combo.currentText()
        conn = db_connect()
        try:
            data = db_get_valid_games(conn, season)
            if not data:
                QMessageBox.warning(self, "No Games Cached", "Please fetch games for this season first.")
                return
            games = data.get("response", [])
        finally:
            conn.close()
        results = []
        for game in games:
            game_id = game["id"]
            try:
                conn = db_connect()
                try:
                    stats_data = db_get_valid_stats(conn, game_id)
                finally:
                    conn.close()
                if not stats_data:
                    continue
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
    db_init()
    app = QApplication(sys.argv)
    window = NBAWatchApp()
    window.show()
    sys.exit(app.exec_()) 
