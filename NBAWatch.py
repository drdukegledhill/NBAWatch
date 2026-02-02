import os
import sys
import requests
import json
import time
import sqlite3
import threading
from collections import deque
from dotenv import load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QSizePolicy, QStackedWidget
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal, QTimer

load_dotenv()
API_KEY = os.environ.get("NBAWATCH_API_KEY", "YOUR_API_KEY")
SEASONS = ["2021", "2022", "2023","2024"]  # Only allowed seasons for free plan
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nba_cache.sqlite")


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


def db_save_stats(conn, game_id, data, commit=True):
    payload = json.dumps(data)
    conn.execute(
        "INSERT OR REPLACE INTO stats (game_id, json, updated_at) VALUES (?, ?, ?)",
        (game_id, payload, int(time.time())),
    )
    if commit:
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
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._pause_event.set()

    def resume(self):
        self._pause_event.clear()

    def _wait_if_paused(self):
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.2)

    def _sleep_interruptible(self, seconds):
        step = 0.2
        remaining = float(seconds)
        while remaining > 0 and not self._stop_event.is_set():
            self._wait_if_paused()
            time.sleep(min(step, remaining))
            remaining -= step
        return not self._stop_event.is_set()

    def run(self):
        conn = db_connect()
        session = requests.Session()
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
        session.headers.update(headers)
        backoff = 15
        max_backoff = 300
        pending_commits = 0

        while missing and not self._stop_event.is_set():
            self._wait_if_paused()
            game_id = missing[0]
            if db_get_valid_stats(conn, game_id):
                missing.popleft()
                done += 1
                self.progress.emit(total, done, f"Cached {done}/{total} games for {self.season}.")
                continue

            url = f"https://v2.nba.api-sports.io/games/statistics?id={game_id}"
            try:
                response = session.get(url, timeout=20)
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
                    db_save_stats(conn, game_id, data, commit=False)
                    pending_commits += 1
                    if pending_commits >= 10:
                        conn.commit()
                        pending_commits = 0
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

        if pending_commits:
            conn.commit()
        if self._stop_event.is_set():
            self.progress.emit(total, done, "Caching stopped.")
        else:
            self.progress.emit(total, done, f"All stats cached for season {self.season}.")
        self.finished.emit()
        session.close()
        conn.close()


class CacheScanWorker(QObject):
    progress = pyqtSignal(int, int)  # total, done
    finished = pyqtSignal(int, int)  # total, done

    def __init__(self, game_ids):
        super().__init__()
        self.game_ids = list(game_ids)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        total = len(self.game_ids)
        done = 0
        if total == 0:
            self.progress.emit(0, 0)
            self.finished.emit(0, 0)
            return
        conn = db_connect()
        try:
            for idx, game_id in enumerate(self.game_ids, start=1):
                if self._stop_event.is_set():
                    break
                if db_get_valid_stats(conn, game_id):
                    done += 1
                if idx == total or idx % 25 == 0:
                    self.progress.emit(total, done)
        finally:
            conn.close()
        self.finished.emit(total, done)

class NBAWatchApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NBAWatch: Season & Game Selector")
        self.setGeometry(100, 100, 1200, 700)
        self.layout = QHBoxLayout()
        self.left_panel = QVBoxLayout()
        self.right_panel = QVBoxLayout()

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

        self.left_panel.addLayout(self.season_row)

        self.api_status = QLabel("API: idle")
        self.left_panel.addWidget(self.api_status)

        self.cache_status = QLabel("Stats cache: idle")
        self.left_panel.addWidget(self.cache_status)
        self.cache_progress = QProgressBar()
        self.cache_progress.setMinimum(0)
        self.cache_progress.setValue(0)
        self.left_panel.addWidget(self.cache_progress)
        self.cache_scan_status = QLabel("")
        self.cache_scan_status.setStyleSheet("color: #666; font-size: 12px;")
        self.left_panel.addWidget(self.cache_scan_status)
        self.scan_dots_timer = QTimer(self)
        self.scan_dots_timer.timeout.connect(self._tick_scan_indicator)
        self.scan_dots_phase = 0

        self.game_label = QLabel("Select Game:")
        self.left_panel.addWidget(self.game_label)

        self.game_combo = QComboBox()
        self.left_panel.addWidget(self.game_combo)

        self.get_stats_btn = QPushButton("Get Game Stats")
        self.get_stats_btn.clicked.connect(self.fetch_game_stats)
        self.left_panel.addWidget(self.get_stats_btn)

        # Team info and stats table
        self.display_stack = QStackedWidget()
        self.right_panel.addWidget(self.display_stack)

        self.game_view = QWidget()
        self.game_view_layout = QVBoxLayout()
        self.game_view.setLayout(self.game_view_layout)

        self.teams_row = QHBoxLayout()
        self.team1_box = QVBoxLayout()
        self.team2_box = QVBoxLayout()
        self.teams_row.addLayout(self.team1_box)
        self.teams_row.addLayout(self.team2_box)
        self.game_view_layout.addLayout(self.teams_row)

        self.stats_table = QTableWidget()
        self.stats_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stats_table.verticalHeader().setVisible(False)
        self.game_view_layout.addWidget(self.stats_table)

        # Add Rewatch Score label
        self.rewatch_label = QLabel("Rewatch Score: N/A")
        self.rewatch_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px 0;")
        self.game_view_layout.addWidget(self.rewatch_label)

        self.rank_btn = QPushButton("Build Season Rewatch Rankings")
        self.rank_btn.setToolTip("Requires full season stats cache")
        self.rank_btn.setEnabled(False)
        self.rank_btn.clicked.connect(self.build_season_rankings)
        self.left_panel.addWidget(self.rank_btn)

        self.rank_view = QWidget()
        self.rank_view_layout = QVBoxLayout()
        self.rank_view.setLayout(self.rank_view_layout)

        self.rank_table = QTableWidget()
        self.rank_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.rank_table.verticalHeader().setVisible(False)
        self.rank_view_layout.addWidget(self.rank_table)

        self.display_stack.addWidget(self.game_view)
        self.display_stack.addWidget(self.rank_view)
        self.display_stack.setCurrentWidget(self.game_view)

        # Add Quit button at the bottom right
        self.quit_row = QHBoxLayout()
        self.quit_row.addStretch()
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.clicked.connect(QApplication.instance().quit)
        self.quit_row.addWidget(self.quit_btn)
        self.left_panel.addStretch()
        self.left_panel.addLayout(self.quit_row)

        self.layout.addLayout(self.left_panel, 1)
        self.layout.addLayout(self.right_panel, 2)
        self.setLayout(self.layout)
        self.cache_thread = None
        self.cache_worker = None
        self.scan_thread = None
        self.scan_worker = None
        self.cache_game_ids = []  # Track games being cached
        self.cache_season = None  # Track season being cached
        self.pending_cache_games = []
        self.cache_completed = False
        self.games_by_id = {}
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop_stats_cache_worker)
        if API_KEY == "YOUR_API_KEY":
            self.api_status.setText("API: missing key (set NBAWATCH_API_KEY or edit NBAWatch.py)")
            QMessageBox.warning(
                self,
                "Missing API Key",
                "Set NBAWATCH_API_KEY in your environment or replace API_KEY in NBAWatch.py.",
            )

    def fetch_games(self, force_refresh=False):
        season = self.season_combo.currentText()
        self.cache_completed = False
        self.rank_btn.setEnabled(False)
        self.stop_cache_scan_worker()
        self.cache_scan_status.setText("")
        games_data = None
        self.api_status.setText("API: fetching games...")
        # Try to load from cache unless force_refresh
        if not force_refresh:
            conn = db_connect()
            try:
                data = db_get_valid_games(conn, season)
                if data:
                    games_data = data.get("response", [])
                    self.api_status.setText("API: games loaded from cache")
            except Exception as e:
                print("Cache load error:", e)
                self.api_status.setText(f"API: cache load error: {e}")
                games_data = None
            finally:
                conn.close()
        if games_data is None:
            url = f"https://v2.nba.api-sports.io/games?season={season}"
            headers = {"x-apisports-key": API_KEY}
            try:
                response = requests.get(url, headers=headers, timeout=20)
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

        game_ids = [g.get("id") for g in games if g.get("id")]
        self.pending_cache_games = list(games)
        self.start_cache_scan_worker(game_ids, season)

    def start_stats_cache_worker(self, games, season):
        # Only start if one isn't already running
        if self.cache_thread is not None and self.cache_thread.isRunning():
            return  # Let existing thread finish
        
        self.cache_completed = False
        self.rank_btn.setEnabled(False)
        game_ids = [g.get("id") for g in games if g.get("id")]
        self.cache_game_ids = game_ids
        self.cache_season = season
        self.cache_worker = StatsCacheWorker(game_ids, season, API_KEY)
        self.cache_thread = QThread()
        self.cache_worker.moveToThread(self.cache_thread)
        self.cache_thread.started.connect(self.cache_worker.run)
        self.cache_worker.progress.connect(self.on_cache_progress)
        self.cache_worker.finished.connect(self.on_cache_finished)
        self.cache_worker.finished.connect(self.cache_thread.quit)
        self.cache_thread.finished.connect(self.on_cache_thread_finished)
        self.cache_thread.start()

    def stop_stats_cache_worker(self):
        """Only called on app close - let thread finish naturally"""
        if self.cache_worker is not None:
            self.cache_worker.stop()
        if self.cache_thread is not None and self.cache_thread.isRunning():
            self.cache_thread.quit()
            # Give thread a reasonable time to finish
            self.cache_thread.wait(3000)

    def start_cache_scan_worker(self, game_ids, season):
        if self.scan_thread is not None and self.scan_thread.isRunning():
            return
        self.cache_progress.setMaximum(max(len(game_ids), 1))
        self.cache_progress.setValue(0)
        self.cache_status.setText(f"Stats cache: scanning cached data for season {season}...")
        self.scan_dots_phase = 0
        self.cache_scan_status.setText("Scanning cache")
        self.scan_dots_timer.start(300)
        self.scan_worker = CacheScanWorker(game_ids)
        self.scan_thread = QThread()
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(lambda total, done: self.on_cache_scan_progress(total, done, season))
        self.scan_worker.finished.connect(lambda total, done: self.on_cache_scan_finished(total, done, season))
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self.on_cache_scan_thread_finished)
        self.scan_thread.start()

    def stop_cache_scan_worker(self):
        if self.scan_worker is not None:
            self.scan_worker.stop()
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait(3000)

    def pause_stats_cache_worker(self):
        if self.cache_worker is not None:
            self.cache_worker.pause()

    def resume_stats_cache_worker(self):
        if self.cache_worker is not None:
            self.cache_worker.resume()

    def on_cache_progress(self, total, done, status):
        self.cache_progress.setMaximum(max(total, 1))
        self.cache_progress.setValue(done)
        percentage = int((done / total * 100)) if total > 0 else 0
        self.cache_status.setText(f"Stats cache: {status} ({percentage}%)")
        if total > 0 and done >= total:
            self.cache_completed = True
            self.rank_btn.setEnabled(True)

    def on_cache_finished(self):
        self.cache_worker = None
        self.cache_status.setText("Stats cache: idle")

    def on_cache_thread_finished(self):
        # Clean up carefully - thread is already stopped at this point
        self.cache_thread = None
        self.cache_worker = None

    def on_cache_scan_progress(self, total, done, season):
        self.cache_progress.setMaximum(max(total, 1))
        self.cache_progress.setValue(done)
        percentage = int((done / total * 100)) if total > 0 else 0
        self.cache_status.setText(
            f"Stats cache: {done}/{total} cached for season {season} ({percentage}%)"
        )

    def on_cache_scan_finished(self, total, done, season):
        self.scan_worker = None
        self.scan_dots_timer.stop()
        self.cache_scan_status.setText("")
        if total == 0:
            self.cache_status.setText("Stats cache: no games to cache (0%)")
            return
        percentage = int((done / total * 100)) if total > 0 else 0
        if done >= total:
            self.cache_status.setText(f"Stats cache: all cached for season {season} ({percentage}%)")
            self.cache_completed = True
            self.rank_btn.setEnabled(True)
            return
        self.cache_status.setText(
            f"Stats cache: {done}/{total} cached for season {season} ({percentage}%)"
        )
        if self.pending_cache_games:
            self.start_stats_cache_worker(self.pending_cache_games, season)

    def on_cache_scan_thread_finished(self):
        self.scan_thread = None
        self.scan_worker = None

    def closeEvent(self, event):
        self.stop_stats_cache_worker()
        self.stop_cache_scan_worker()
        super().closeEvent(event)

    def _tick_scan_indicator(self):
        self.scan_dots_phase = (self.scan_dots_phase + 1) % 4
        self.cache_scan_status.setText("Scanning cache" + "." * self.scan_dots_phase)

    def fetch_game_stats(self, force_refresh=False):
        self.display_stack.setCurrentWidget(self.game_view)
        cache_was_running = bool(self.cache_thread is not None and self.cache_thread.isRunning())
        if cache_was_running:
            self.pause_stats_cache_worker()
        idx = self.game_combo.currentIndex()
        if idx == -1:
            QMessageBox.warning(self, "No Game Selected", "Please select a game.")
            if cache_was_running:
                self.resume_stats_cache_worker()
            return
        game_id = self.game_combo.itemData(idx)
        if not game_id:
            QMessageBox.warning(self, "No Game Selected", "Please select a valid game.")
            if cache_was_running:
                self.resume_stats_cache_worker()
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
                        self.api_status.setText("API: stats loaded")
                    except Exception as e:
                        print("Stats cache save error:", e)
                        self.api_status.setText(f"API: stats cache save error: {e}")
                else:
                    msg = f"Error: {response.status_code}\n{response.text}"
                    self.api_status.setText(f"API: {msg}")
                    QMessageBox.warning(self, "API Error", msg)
                    if cache_was_running:
                        self.resume_stats_cache_worker()
                    return
            except Exception as e:
                self.api_status.setText(f"API: stats request error: {e}")
                QMessageBox.critical(self, "Error", str(e))
                if cache_was_running:
                    self.resume_stats_cache_worker()
                return
        stats = stats_data
        if len(stats) != 2:
            game = self.games_by_id.get(game_id)
            status = None
            if game:
                status = game.get("status", {}).get("long")
            cached_count = len(stats)
            cached_percentage = int((cached_count / 2) * 100)
            if status and status.lower() != "finished":
                QMessageBox.warning(
                    self,
                    "Stats Not Ready",
                    f"Stats are not available until the game is finished. Status: {status}.\nCached: {cached_percentage}%",
                )
                self.api_status.setText(f"API: stats not ready (status: {status}) - {cached_percentage}% cached")
            else:
                QMessageBox.warning(self, "Stats Error", f"Could not retrieve stats for both teams. {cached_percentage}% cached.")
                self.api_status.setText(f"API: stats incomplete for this game - {cached_percentage}% cached")
            if cache_was_running:
                self.resume_stats_cache_worker()
            return
        self.display_team_info(stats)
        self.display_stats_table(stats)
        if cache_was_running:
            self.resume_stats_cache_worker()

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
        self.set_logo_pixmap(logo1, team1.get("logo"), team1.get("name", ""))
        self.team1_box.addWidget(name1)
        self.team1_box.addWidget(logo1)
        # Team 2
        team2 = stats[1]["team"]
        name2 = QLabel(team2.get("name", ""))
        logo2 = QLabel()
        self.set_logo_pixmap(logo2, team2.get("logo"), team2.get("name", ""))
        self.team2_box.addWidget(name2)
        self.team2_box.addWidget(logo2)

    TEAM_ABBR = {
        "Atlanta Hawks": "ATL",
        "Boston Celtics": "BOS",
        "Brooklyn Nets": "BKN",
        "Charlotte Hornets": "CHA",
        "Chicago Bulls": "CHI",
        "Cleveland Cavaliers": "CLE",
        "Dallas Mavericks": "DAL",
        "Denver Nuggets": "DEN",
        "Detroit Pistons": "DET",
        "Golden State Warriors": "GSW",
        "Houston Rockets": "HOU",
        "Indiana Pacers": "IND",
        "LA Clippers": "LAC",
        "L.A. Clippers": "LAC",
        "Los Angeles Clippers": "LAC",
        "LA Lakers": "LAL",
        "L.A. Lakers": "LAL",
        "Los Angeles Lakers": "LAL",
        "Memphis Grizzlies": "MEM",
        "Miami Heat": "MIA",
        "Milwaukee Bucks": "MIL",
        "Minnesota Timberwolves": "MIN",
        "New Orleans Pelicans": "NOP",
        "New Orleans Hornets": "NOP",
        "New York Knicks": "NYK",
        "Oklahoma City Thunder": "OKC",
        "Orlando Magic": "ORL",
        "Philadelphia 76ers": "PHI",
        "Philadelphia Sixers": "PHI",
        "Phoenix Suns": "PHX",
        "Portland Trailblazers": "POR",
        "Portland Trail Blazers": "POR",
        "Sacramento Kings": "SAC",
        "San Antonio Spurs": "SAS",
        "Toronto Raptors": "TOR",
        "Utah Jazz": "UTA",
        "Washington Wizards": "WAS",
    }

    def _team_abbr(self, team_name):
        if not team_name:
            return None
        return self.TEAM_ABBR.get(team_name)

    def _load_pixmap_from_url(self, url):
        if not url:
            return None
        try:
            print("Loading logo from:", url)
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code != 200:
                return None
            img_data = response.content
            pixmap = QPixmap()
            if pixmap.loadFromData(img_data) and not pixmap.isNull():
                return pixmap
        except Exception as e:
            print("Logo load error:", e)
        return None

    def set_logo_pixmap(self, label, url, team_name=""):
        pixmap = self._load_pixmap_from_url(url)
        if pixmap is None:
            abbr = self._team_abbr(team_name)
            if abbr:
                fallback_url = f"https://a.espncdn.com/i/teamlogos/nba/500/{abbr}.png"
                pixmap = self._load_pixmap_from_url(fallback_url)
        if pixmap is not None:
            pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(pixmap)
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
        stat_dicts = self.build_stat_dicts(stats)

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

    def build_stat_dicts(self, stats):
        stat_dicts = []
        for team_stats in stats:
            statistics = team_stats.get("statistics")
            if isinstance(statistics, list):
                if statistics and isinstance(statistics[0], dict) and "type" not in statistics[0]:
                    stat_dict = statistics[0]
                else:
                    stat_dict = {}
                    for item in statistics:
                        if isinstance(item, dict) and "type" in item and "value" in item:
                            stat_dict[item["type"]] = item["value"]
                stat_dicts.append(stat_dict)
            elif isinstance(statistics, dict):
                stat_dicts.append(statistics)
            else:
                stat_dicts.append({})
        return stat_dicts

    def display_rewatch_score(self, stat_dicts):
        rewatch_score = self.compute_rewatch_score(stat_dicts)
        self.rewatch_label.setText(f"Rewatch Score: {rewatch_score:.1f}")

    def compute_rewatch_score(self, stat_dicts):
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

        return rewatch_score

    def build_season_rankings(self):
        self.display_stack.setCurrentWidget(self.rank_view)
        if not self.cache_completed:
            QMessageBox.warning(self, "Cache Not Ready", "Wait until the season cache is complete.")
            return
        season = self.season_combo.currentText()
        conn = db_connect()
        rankings = []
        skipped = 0
        try:
            for game_id, game in self.games_by_id.items():
                data = db_get_valid_stats(conn, game_id)
                if not data:
                    skipped += 1
                    continue
                stats = data.get("response", [])
                if len(stats) != 2:
                    skipped += 1
                    continue
                stat_dicts = self.build_stat_dicts(stats)
                score = self.compute_rewatch_score(stat_dicts)
                date = ""
                try:
                    date_raw = game.get("date", "")
                    if isinstance(date_raw, dict):
                        date = (date_raw.get("start") or "")[:10]
                    else:
                        date = str(date_raw)[:10]
                except Exception:
                    date = ""
                try:
                    home = game["teams"]["home"]["name"]
                    away = game["teams"]["visitors"]["name"]
                    matchup = f"{away} @ {home}"
                except Exception:
                    matchup = "Unknown matchup"
                rankings.append((score, game_id, date, matchup))
        finally:
            conn.close()

        if not rankings:
            QMessageBox.warning(self, "No Cached Stats", f"No cached stats found for season {season}.")
            return

        rankings.sort(key=lambda r: r[0], reverse=True)

        self.rank_table.clear()
        self.rank_table.setRowCount(len(rankings))
        self.rank_table.setColumnCount(5)
        self.rank_table.setHorizontalHeaderLabels(
            ["Rank", "Date", "Matchup", "Game ID", "Rewatch Score"]
        )

        for row, (score, game_id, date, matchup) in enumerate(rankings, start=1):
            self.rank_table.setItem(row - 1, 0, QTableWidgetItem(str(row)))
            self.rank_table.setItem(row - 1, 1, QTableWidgetItem(date))
            self.rank_table.setItem(row - 1, 2, QTableWidgetItem(matchup))
            self.rank_table.setItem(row - 1, 3, QTableWidgetItem(str(game_id)))
            self.rank_table.setItem(row - 1, 4, QTableWidgetItem(f"{score:.1f}"))

        self.rank_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if skipped:
            self.api_status.setText(
                f"API: rankings built for {season} (skipped {skipped} games with missing stats)"
            )
        else:
            self.api_status.setText(f"API: rankings built for {season}")


if __name__ == "__main__":
    db_init()
    app = QApplication(sys.argv)
    window = NBAWatchApp()
    window.show()
    sys.exit(app.exec_()) 
