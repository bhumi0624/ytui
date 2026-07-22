#!/usr/bin/env python3
"""
ytui - yt-dlp Terminal User Interface
Single-file curses TUI for Termux Android.
"""

import curses
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "ytui"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

DEFAULT_CONFIG = {
    "last_dir": "/sdcard/Download",
    "default_format": "bv*[height<=1080]+ba/b[height<=1080]",
    "max_history": 100,
    "theme": "dark",
}

COLOR_MENU = 1
COLOR_TITLE = 2
COLOR_SEL = 3
COLOR_STATUS = 4
COLOR_PROGRESS = 5
COLOR_HEADER = 6
COLOR_INFO = 7
COLOR_ERROR = 8

# ── Theme definitions ──────────────────────────────────────────
THEME_DARK = {
    "menu":      (curses.COLOR_WHITE, -1),
    "title":     (curses.COLOR_CYAN, -1),
    "sel":       (curses.COLOR_YELLOW, -1),
    "status":    (curses.COLOR_BLACK, curses.COLOR_WHITE),
    "progress":  (curses.COLOR_GREEN, -1),
    "header":    (curses.COLOR_CYAN, -1),
    "info":      (curses.COLOR_MAGENTA, -1),
    "error":     (curses.COLOR_RED, -1),
}

THEME_LIGHT = {
    "menu":      (curses.COLOR_BLACK, -1),
    "title":     (curses.COLOR_BLUE, -1),
    "sel":       (curses.COLOR_WHITE, curses.COLOR_BLUE),
    "status":    (curses.COLOR_WHITE, curses.COLOR_BLUE),
    "progress":  (curses.COLOR_GREEN, -1),
    "header":    (curses.COLOR_BLUE, -1),
    "info":      (curses.COLOR_MAGENTA, -1),
    "error":     (curses.COLOR_RED, -1),
}

THEMES = {"dark": THEME_DARK, "light": THEME_LIGHT}

COLOR_NAMES = {
    1: "menu", 2: "title", 3: "sel", 4: "status",
    5: "progress", 6: "header", 7: "info", 8: "error",
}


class ConfigManager:
    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE) as f:
                    loaded = json.load(f)
                    self.data = {**DEFAULT_CONFIG, **loaded}
        except (json.JSONDecodeError, OSError):
            pass

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULT_CONFIG.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()


class HistoryManager:
    def __init__(self, config):
        self.config = config
        self.entries = []
        self.load()

    def load(self):
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE) as f:
                    self.entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.entries = []

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.entries, f, indent=2)
        except OSError:
            pass

    def add(self, url, title, format_id, format_note, path, status="success"):
        entry = {
            "url": url,
            "title": title,
            "format_id": format_id,
            "format_note": format_note,
            "path": path,
            "timestamp": datetime.now().isoformat(),
            "status": status,
        }
        self.entries.insert(0, entry)
        max_h = self.config["max_history"]
        if len(self.entries) > max_h:
            self.entries = self.entries[:max_h]
        self.save()

    def delete(self, index):
        if 0 <= index < len(self.entries):
            del self.entries[index]
            self.save()

    def clear(self):
        self.entries = []
        self.save()

    def format_size(self, size_str):
        try:
            size = float(size_str)
            for unit in ["B", "KB", "MiB", "GiB"]:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} GiB"
        except (ValueError, TypeError):
            return size_str or ""


def fmt_filesize(bytes_val):
    if not bytes_val:
        return "?"
    try:
        b = float(bytes_val)
        for unit in ["B", "KB", "MiB", "GiB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} GiB"
    except (ValueError, TypeError):
        return "?"


def fmt_speed(bytes_per_sec):
    if not bytes_per_sec:
        return "?"
    try:
        bps = float(bytes_per_sec)
        if bps <= 0:
            return "0"
        for unit in ["B/s", "KB/s", "MiB/s", "GiB/s"]:
            if bps < 1024:
                return f"{bps:.1f} {unit}"
            bps /= 1024
        return f"{bps:.1f} GiB/s"
    except (ValueError, TypeError):
        return str(bytes_per_sec)


def fmt_eta(sec_str):
    if not sec_str or sec_str in ("NA", "N/A", "Unknown", "0", "0:00"):
        return ""
    try:
        secs = float(sec_str)
        if secs <= 0:
            return ""
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except (ValueError, TypeError):
        return str(sec_str)


def sanitize_filename(name, max_len=80):
    """Bersihkan string untuk jadi nama folder/file, ganti spasi dgn underscore."""
    if not name:
        return "untitled"
    # Hanya允许 alfanumerik, spasi, underscore, strip, hyphen
    clean = re.sub(r'[^\w\s\-]', '', name).strip()
    clean = re.sub(r'\s+', '_', clean)
    clean = clean[:max_len].rstrip('_') or "untitled"
    return clean


def fmt_time(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%d %b %H:%M")
    except (ValueError, TypeError):
        return ts_str


class Screen:
    def __init__(self, app):
        self.app = app

    def render(self):
        raise NotImplementedError

    def handle_key(self, key):
        raise NotImplementedError

    def handle_mouse(self):
        """Handle mouse click. Override in subclass if needed."""
        pass

    def draw_button(self, y, x, text, width=20, selected=False, active=False):
        """Draw a clickable button with box-drawing characters.
        Returns (y, x, width, height=3) for hit-testing.
        """
        h, w = self.app.stdscr.getmaxyx()
        if y < 0 or y + 2 >= h or x < 0 or x + width >= w:
            return (y, x, width, 3)  # skip rendering if offscreen
        attr_btn = curses.color_pair(COLOR_SEL) | (curses.A_REVERSE if selected else 0)
        attr_frame = curses.color_pair(COLOR_MENU)
        if active:
            attr_btn |= curses.A_BOLD
        try:
            # Top border
            self.app.stdscr.attron(attr_frame)
            self.app.stdscr.addstr(y, x, "┌" + "─" * (width - 2) + "┐")
            self.app.stdscr.attroff(attr_frame)
            # Text line
            padded = f" {text:^{width-4}} "
            self.app.stdscr.attron(attr_btn)
            self.app.stdscr.addstr(y + 1, x, "│" + padded[:width - 2] + "│")
            self.app.stdscr.attroff(attr_btn)
            # Bottom border
            self.app.stdscr.attron(attr_frame)
            self.app.stdscr.addstr(y + 2, x, "└" + "─" * (width - 2) + "┘")
            self.app.stdscr.attroff(attr_frame)
        except curses.error:
            pass
        return (y, x, width, 3)

    def draw_status(self, text="", color=COLOR_STATUS):
        h, w = self.app.stdscr.getmaxyx()
        sep_y = h - 3
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER))
            self.app.stdscr.addstr(sep_y, 0, "─" * w)
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER))
        except curses.error:
            pass
        try:
            self.app.stdscr.attron(curses.color_pair(color))
            self.app.stdscr.addstr(sep_y + 1, 0, text[:w - 1])
            self.app.stdscr.attroff(curses.color_pair(color))
        except curses.error:
            pass

    def draw_title(self, text):
        h, w = self.app.stdscr.getmaxyx()
        title = f" ytui v1.0: {text} "
        pad = w - len(title) - 2
        if pad < 0:
            title = title[:w - 4]
            pad = 0
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            self.app.stdscr.addstr(0, 0, f"┌{title}{'─' * pad}┐")
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        except curses.error:
            pass

    def clear_content(self):
        h, w = self.app.stdscr.getmaxyx()
        for y in range(1, h - 3):
            try:
                self.app.stdscr.addstr(y, 0, " " * (w - 1))
            except curses.error:
                pass


class MainMenu(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.items = [
            ("Search YouTube", "search"),
            ("Download URL", "download_url"),
            ("Batch Download (from file)", "batch"),
            ("Download History", "history"),
            ("Settings", "settings"),
            ("Exit", "exit"),
        ]
        self.idx = 0
        self._theme_btn = None  # (y, x, w, h) for mouse hit-test

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()

        box_w = 38
        box_x = max(0, w // 2 - box_w // 2)
        box_y = max(0, h // 2 - 6)

        def put(y, s):
            try:
                self.app.stdscr.addstr(y, box_x, s[:box_w])
            except curses.error:
                pass

        # Top
        self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        put(box_y, "╔" + "═" * (box_w - 2) + "╗")
        put(box_y + 1, f"║{'ytui v1.0':^{box_w-2}}║")
        put(box_y + 2, f"║{'yt-dlp Terminal UI':^{box_w-2}}║")
        self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        put(box_y + 3, "╠" + "═" * (box_w - 2) + "╣")

        # Menu items
        for i, (label, _) in enumerate(self.items):
            y = box_y + 4 + i
            prefix = "▶" if i == self.idx else " "
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.idx else curses.color_pair(COLOR_MENU)
            self.app.stdscr.attron(attr)
            put(y, f"║ {prefix} {label:<29} ║")
            self.app.stdscr.attroff(attr)

        # Separator before theme
        item_end = box_y + 4 + len(self.items)
        put(item_end, "╠" + "═" * (box_w - 2) + "╣")

        # Theme inline
        theme = self.app.config["theme"]
        dot = "●" if theme == "dark" else "○"
        btn_y = item_end + 1
        self.app.stdscr.attron(curses.color_pair(COLOR_MENU))
        put(btn_y, f"║   {dot} Theme: {theme.capitalize():<22} ║")
        self.app.stdscr.attroff(curses.color_pair(COLOR_MENU))
        self._theme_btn = (btn_y, box_x, box_w, 1)

        # Bottom
        put(btn_y + 1, "╚" + "═" * (box_w - 2) + "╝")

        self.draw_status("↑/↓ navigate  Enter select  q quit  Ctrl+T toggle theme")

    def _handle_mouse_click(self):
        """Check if mouse click hit the theme button."""
        try:
            _, mx, my, _, bstate = curses.getmouse()
            if bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED):
                if self._theme_btn:
                    btn_y, btn_x, btn_w, btn_h = self._theme_btn
                    if btn_y <= my <= btn_y + btn_h - 1 and btn_x <= mx <= btn_x + btn_w:
                        self.app.toggle_theme()
        except curses.error:
            pass

    def handle_mouse(self):
        self._handle_mouse_click()

    def handle_key(self, key):
        if key == curses.KEY_MOUSE:
            self._handle_mouse_click()
        elif key == 20:  # Ctrl+T — toggle theme
            self.app.toggle_theme()
        elif key in (ord("q"), 27):
            self.app.running = False
        elif key == curses.KEY_UP:
            self.idx = (self.idx - 1) % len(self.items)
        elif key == curses.KEY_DOWN:
            self.idx = (self.idx + 1) % len(self.items)
        elif key in (curses.KEY_ENTER, 10, 13):
            action = self.items[self.idx][1]
            if action == "search":
                self.app.push_screen(SearchInput(self.app))
            elif action == "download_url":
                self.app.push_screen(URLInput(self.app))
            elif action == "batch":
                self.app.push_screen(BatchDownload(self.app))
            elif action == "history":
                self.app.push_screen(HistoryView(self.app))
            elif action == "settings":
                self.app.push_screen(SettingsView(self.app))
            elif action == "exit":
                self.app.running = False


class URLInput(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.url = app.start_url or ""
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Download URL")

        lines = [
            "Paste or type a video/playlist URL below, then press Enter.",
            "",
            "URL: " + self.url + ("█" if len(self.url) < w - 10 else ""),
        ]
        if self.msg:
            lines.append("")
            lines.append(self.msg)

        for i, line in enumerate(lines):
            try:
                attr = curses.color_pair(COLOR_ERROR) if self.msg and i == len(lines) - 1 else curses.color_pair(COLOR_MENU)
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(h // 2 - 2 + i, 4, line[: w - 8])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        self.draw_status("Enter confirm  Esc back  Ctrl+U clear")

    def handle_key(self, key):
        if key == 27:
            self.app.pop_screen()
        elif key == 21:
            self.url = ""
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.url.strip():
                # Route ke PlaylistDetect yang akan auto-detect playlist vs single
                self.app.push_screen(PlaylistDetect(self.app, self.url.strip()))
            else:
                self.msg = "URL cannot be empty!"
        elif key == curses.KEY_BACKSPACE or key == 127:
            self.url = self.url[:-1]
            self.msg = ""
        elif key in (curses.KEY_RESIZE,):
            pass
        elif key == 22:  # Ctrl+V
            clipboard = shutil.which("termux-clipboard-get")
            if clipboard:
                try:
                    paste = subprocess.check_output([clipboard], timeout=2).decode().strip()
                    self.url += paste
                    self.msg = ""
                except Exception:
                    self.msg = "Clipboard paste failed"
            else:
                self.msg = "Clipboard not available (install termux-api)"
        elif 32 <= key < 127:
            self.url += chr(key)
            self.msg = ""


class SearchInput(Screen):
    """Search YouTube videos via yt-dlp ytsearch: and pick from results."""
    def __init__(self, app):
        super().__init__(app)
        self.query = ""
        self.results = []
        self.idx = 0
        self.offset = 0
        self.mode = "input"  # "input" | "loading" | "results"
        self.error = ""
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Search YouTube")

        if self.mode == "loading":
            try:
                msg = " Searching YouTube... "
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
                self.app.stdscr.addstr(h // 2, w // 2 - len(msg) // 2, msg)
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
            except curses.error:
                pass
            self.draw_status("Searching...  Esc cancel")
            return

        if self.mode == "results":
            self._render_results(h, w)
            return

        # mode == "input"
        lines = [
            "Search for videos on YouTube. Results are fetched via yt-dlp.",
            "",
            "Search: " + self.query + ("█" if len(self.query) < w - 10 else ""),
        ]
        if self.msg:
            lines.append("")
            lines.append(self.msg)

        for i, line in enumerate(lines):
            try:
                attr = curses.color_pair(COLOR_ERROR) if self.msg and i == len(lines) - 1 else curses.color_pair(COLOR_MENU)
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(h // 2 - 2 + i, 4, line[: w - 8])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        self.draw_status("Enter search  Esc back  Ctrl+U clear")

    def _render_results(self, h, w):
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(1, 0, f" Results for: {self.query[:w-16]}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        header = f"{'':4}{'Title':<50}  {'Channel':<20}  {'Dur':6}"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
            self.app.stdscr.addstr(2, 0, header[:w - 1])
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        max_visible = h - 6
        if self.idx < self.offset:
            self.offset = self.idx
        if self.idx >= self.offset + max_visible:
            self.offset = self.idx - max_visible + 1

        for i, r in enumerate(self.results[self.offset:self.offset + max_visible]):
            y = 3 + i
            num = f"{self.offset + i + 1:>3}."
            title = r.get('title', '?')[:48]
            channel = r.get('channel', '?')[:18]
            dur = r.get('duration', 0)
            mins, secs = divmod(int(dur), 60)
            hours, mins = divmod(mins, 60)
            dur_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}" if dur else "?:??"
            line = f" {num} {title:<50}  {channel:<20}  {dur_str:>6}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if (self.offset + i) == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 0, line[:w - 1])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        # Stats
        stats = f" {len(self.results)} results  showing {self.offset + 1}-{min(self.offset + max_visible, len(self.results))}"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(h - 3, 2, stats[:w - 4])
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        if self.error:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.app.stdscr.addstr(h - 4, 2, f" {self.error[:w-4]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except curses.error:
                pass

        self.draw_status("↑/↓ navigate  Enter select  Esc back  n new search")

    def handle_key(self, key):
        if self.mode == "loading":
            if key == 27:
                self.mode = "input"
                self.msg = "Search cancelled"
            return

        if self.mode == "results":
            self._handle_results_key(key)
            return

        # mode == "input"
        if key == 27:
            self.app.pop_screen()
        elif key == 21:  # Ctrl+U
            self.query = ""
            self.msg = ""
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.query.strip():
                self._do_search()
            else:
                self.msg = "Query cannot be empty!"
        elif key == curses.KEY_BACKSPACE or key == 127:
            self.query = self.query[:-1]
            self.msg = ""
        elif key == 22:  # Ctrl+V
            clipboard = shutil.which("termux-clipboard-get")
            if clipboard:
                try:
                    paste = subprocess.check_output([clipboard], timeout=2).decode().strip()
                    self.query += paste
                    self.msg = ""
                except Exception:
                    self.msg = "Clipboard paste failed"
            else:
                self.msg = "Clipboard not available (install termux-api)"
        elif 32 <= key < 127:
            self.query += chr(key)
            self.msg = ""

    def _handle_results_key(self, key):
        if key == 27:
            self.mode = "input"
            self.msg = ""
            self.query = ""
        elif key in (ord("n"), ord("N")):
            self.mode = "input"
            self.query = ""
            self.results = []
            self.msg = ""
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(len(self.results) - 1, self.idx + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.results:
                selected = self.results[self.idx]
                url = selected.get('url', '')
                if url:
                    self.app.push_screen(FormatSelector(self.app, url))

    def _do_search(self):
        self.mode = "loading"
        self.error = ""
        self.results = []
        self.idx = 0
        self.offset = 0

        def run():
            try:
                # Escape special regex chars in query — ytsearch handles plain text
                search_q = self.query.strip()
                result = subprocess.run(
                    ["yt-dlp", "--flat-playlist", "--dump-json",
                     f"ytsearch15:{search_q}"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    self.error = result.stderr.strip()[:100]
                    self.mode = "input"
                    return
                lines = [l for l in result.stdout.strip().split('\n') if l]
                for line in lines:
                    try:
                        d = json.loads(line)
                        vid_url = d.get('original_url') or d.get('webpage_url') or \
                                   f"https://youtube.com/watch?v={d.get('id', '')}"
                        ch = d.get('channel') or d.get('uploader') or d.get('channel_url') or '?'
                        if ch and ch.startswith('http'):
                            ch = '?'
                        self.results.append({
                            'id': d.get('id', ''),
                            'title': d.get('title', '?'),
                            'url': vid_url,
                            'channel': ch[:30],
                            'duration': d.get('duration', 0),
                            'views': d.get('view_count', 0),
                        })
                    except json.JSONDecodeError:
                        continue
                if not self.results:
                    self.error = "No results found"
                    self.mode = "input"
                else:
                    self.mode = "results"
            except subprocess.TimeoutExpired:
                self.error = "Search timed out after 30s"
                self.mode = "input"
            except FileNotFoundError:
                self.error = "yt-dlp not found! Install with: pkg install yt-dlp"
                self.mode = "input"
            except Exception as e:
                self.error = str(e)[:100]
                self.mode = "input"

        threading.Thread(target=run, daemon=True).start()


class FormatSelector(Screen):
    def __init__(self, app, url, playlist_videos=None, playlist_title=""):
        super().__init__(app)
        self.url = url
        self.playlist_videos = playlist_videos  # list of video dicts, or None for single
        self.playlist_title = playlist_title
        self.formats = []
        self.video_info = {}
        self.idx = 0
        self.offset = 0
        self.loading = True
        self.error = ""
        self._fetch()

    def _fetch(self):
        def run():
            try:
                result = subprocess.run(
                    ["yt-dlp", "--dump-json", self.url],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    self.error = result.stderr.strip() or f"yt-dlp exited with code {result.returncode}"
                    self.loading = False
                    return
                data = json.loads(result.stdout)
                formats = data.get("formats", [])
                if not formats:
                    formats = [{
                        "format_id": "best", "ext": "mp4",
                        "width": 0, "height": 0, "filesize": None,
                        "tbr": 0, "vcodec": "none", "acodec": "none",
                        "format_note": "best quality"
                    }]
                parsed = []
                seen = set()
                for f in formats:
                    fid = f.get("format_id", "?")
                    if fid in seen:
                        continue
                    seen.add(fid)
                    height = f.get("height") or 0
                    width = f.get("width") or 0
                    res = f"{height}p" if height else ""
                    if width and height:
                        res = f"{width}x{height}"
                    elif not height and f.get("vcodec") == "none":
                        abr = f.get("abr") or 0
                        res = f"{abr:.0f}k" if abr else "audio"
                    ext = f.get("ext", "?")
                    size = f.get("filesize") or f.get("filesize_approx") or 0
                    tbr = f.get("tbr") or 0
                    vcodec = f.get("vcodec", "none")[:8]
                    acodec = f.get("acodec", "none")[:8]
                    note = f.get("format_note", "")
                    parsed.append({
                        "id": fid,
                        "ext": ext,
                        "res": res,
                        "size": int(size) if size else 0,
                        "tbr": f"{tbr:.0f}" if tbr else "?",
                        "vcodec": vcodec,
                        "acodec": acodec,
                        "note": note[:15],
                    })
                self.formats = parsed
                self.video_info = {
                    "title": data.get("title", "Unknown"),
                    "duration": data.get("duration", 0),
                    "uploader": data.get("uploader", ""),
                    "playlist_count": data.get("playlist_count"),
                    "playlist": data.get("playlist"),
                }
            except subprocess.TimeoutExpired:
                self.error = "yt-dlp timed out after 30s"
            except json.JSONDecodeError:
                self.error = "Failed to parse yt-dlp output"
            except FileNotFoundError:
                self.error = "yt-dlp not found! Install with: pkg install yt-dlp"
            except Exception as e:
                self.error = str(e)
            self.loading = False
        threading.Thread(target=run, daemon=True).start()

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()

        if self.loading:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
            msg = " Fetching formats... "
            self.app.stdscr.addstr(h // 2, w // 2 - len(msg) // 2, msg)
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
            self.draw_status("Loading...")
            return

        if self.error:
            self.app.stdscr.attron(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
            for i, line in enumerate(self.error.split("\n")[:5]):
                self.app.stdscr.addstr(h // 2 - 2 + i, 4, line[: w - 8])
            self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
            try:
                self.app.stdscr.addstr(h // 2 + 3, 4, "Press Esc to go back")
            except curses.error:
                pass
            self.draw_status("Error fetching formats")
            return

        info = self.video_info
        title = info.get("title", "Unknown")
        duration = info.get("duration", 0)
        mins, secs = divmod(int(duration), 60)
        hours, mins = divmod(mins, 60)
        dur_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"

        self.draw_title(f"Select Format - {title[:50]}")

        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            info_line = f" {title[:w-4]}  ({dur_str})"
            self.app.stdscr.addstr(2, 0, info_line[: w - 1])
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        header = f"{'ID':>4}  {'EXT':<6}  {'RES':<10}  {'SIZE':<10}  {'VCODEC':<8}  {'ACODEC':<8}  {'':4}NOTE"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
            self.app.stdscr.addstr(3, 0, header[: w - 1])
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        max_visible = h - 7
        if self.idx < self.offset:
            self.offset = self.idx
        if self.idx >= self.offset + max_visible:
            self.offset = self.idx - max_visible + 1

        for i, f in enumerate(self.formats[self.offset:self.offset + max_visible]):
            y = 4 + i
            size_str = fmt_filesize(f["size"])
            audio_tag = "+a" if f.get("acodec", "") == "none" else ""
            line = f"{f['id']:>4}  {f['ext']:<6}  {f['res']:<10}  {size_str:<10}  {f['vcodec']:<8}  {f['acodec']:<8}  {audio_tag:<4}{f['note']}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if (self.offset + i) == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 0, line[: w - 1])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        footer = f"Showing {len(self.formats)} formats"
        self.draw_status(f"{footer}  ↑/↓ navigate  d download  Esc back")

    def handle_key(self, key):
        if self.loading:
            return
        if self.error:
            if key == 27:
                self.app.pop_screen()
            return
        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(len(self.formats) - 1, self.idx + 1)
        elif key in (curses.KEY_ENTER, 10, 13, ord("d"), ord("D")):
            fmt = self.formats[self.idx]
            pl_name = self.playlist_title if self.playlist_videos else None
            self.app.push_screen(
                FolderBrowser(self.app, self.url, fmt, self.video_info.get("title", ""),
                              playlist_name=pl_name,
                              playlist_videos=self.playlist_videos,
                              playlist_title=self.playlist_title,
                              mp3_mode=False)
            )
        elif key == ord("r"):
            self.loading = True
            self.error = ""
            self.formats = []
            self.idx = 0
            self._fetch()


class FolderBrowser(Screen):
    def __init__(self, app, url, fmt, video_title, playlist_name=None,
                 playlist_videos=None, playlist_title="", mp3_mode=False):
        super().__init__(app)
        self.url = url
        self.fmt = fmt
        self.video_title = video_title
        self.playlist_name = playlist_name
        self.playlist_videos = playlist_videos
        self.playlist_title = playlist_title
        self.mp3_mode = mp3_mode
        self.current_path = app.config["last_dir"]
        self.entries = []
        self.idx = 0
        self.offset = 0
        self.msg = ""
        self.new_folder_mode = False
        self.new_folder_name = ""
        self._browse()

    def _browse(self):
        try:
            path = self.current_path
            items = []
            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                entries = []
                self.msg = "Permission denied"
            for e in entries:
                full = os.path.join(path, e)
                if os.path.isdir(full) and not e.startswith("."):
                    items.append(e)
            self.entries = [".."] + items
            self.idx = 0
            self.offset = 0
        except FileNotFoundError:
            self.entries = [".."]
            self.msg = "Path not found"

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Select Download Directory")

        path_display = self.current_path[: w - 4]
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(2, 0, f" {path_display}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        try:
            audio_tag = " +audio" if self.fmt.get("acodec", "") == "none" else ""
            preview = f"Format: {self.fmt['id']}{audio_tag}  |  {self.video_title[:35]}"
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER))
            self.app.stdscr.addstr(3, 0, f" {preview[:w-3]}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER))
        except curses.error:
            pass

        # Tampilkan nama playlist / MP3 mode
        line3_parts = []
        if self.playlist_name:
            line3_parts.append(f"📁 {self.playlist_name}")
        if self.mp3_mode:
            line3_parts.append("🎵 MP3 Mode")
        if line3_parts:
            try:
                pl_line = "  ".join(line3_parts)
                self.app.stdscr.attron(curses.color_pair(COLOR_PROGRESS))
                self.app.stdscr.addstr(4, 0, f" {pl_line[:w-3]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_PROGRESS))
            except curses.error:
                pass
        y_start = 6 if line3_parts else 5

        max_visible = h - y_start - 3
        if self.idx < self.offset:
            self.offset = self.idx
        if self.idx >= self.offset + max_visible:
            self.offset = self.idx - max_visible + 1

        for i, entry in enumerate(self.entries[self.offset:self.offset + max_visible]):
            y = y_start + i
            prefix = "  "
            if entry == "..":
                display = "[..] Parent Directory"
            else:
                display = entry
            if (self.offset + i) == self.idx:
                prefix = " >"
                attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE
            else:
                attr = curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 2, f"{prefix} {display:<{w-8}}")
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        if self.new_folder_mode:
            try:
                input_line = f" New folder: {self.new_folder_name}█"
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(h - 4, 2, input_line[: w - 4])
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass
        elif self.msg:
            try:
                color = COLOR_INFO if "Created" in self.msg else COLOR_ERROR
                self.app.stdscr.attron(curses.color_pair(color))
                self.app.stdscr.addstr(h - 4, 2, f" {self.msg[:w-4]}")
                self.app.stdscr.attroff(curses.color_pair(color))
            except curses.error:
                pass

        status = "Enter name, Enter confirm, Esc cancel" if self.new_folder_mode else "↑/↓ navigate  Enter select  n new folder  d download  Esc back"
        self.draw_status(status)

    def handle_key(self, key):
        if self.new_folder_mode:
            if key == 27:
                self.new_folder_mode = False
                self.new_folder_name = ""
                self.msg = ""
            elif key in (curses.KEY_ENTER, 10, 13):
                name = self.new_folder_name.strip()
                if name:
                    try:
                        full_path = os.path.join(self.current_path, name)
                        os.makedirs(full_path, exist_ok=True)
                        self.current_path = full_path
                        self.msg = f"Created: {name}"
                        self.new_folder_mode = False
                        self.new_folder_name = ""
                        self._browse()
                    except OSError as e:
                        self.msg = f"Failed: {e}"
                else:
                    self.msg = "Name cannot be empty"
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.new_folder_name = self.new_folder_name[:-1]
            elif 32 <= key < 127:
                self.new_folder_name += chr(key)
            return

        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(len(self.entries) - 1, self.idx + 1)
        elif key in (ord("n"), ord("N")):
            self.new_folder_mode = True
            self.new_folder_name = ""
            self.msg = "Enter folder name:"
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.entries:
                selected = self.entries[self.idx]
                if selected == "..":
                    self.current_path = os.path.dirname(self.current_path.rstrip("/"))
                    self.msg = ""
                else:
                    self.current_path = os.path.join(self.current_path, selected)
                self._browse()
        elif key in (ord("d"), ord("D")):
            path = self.current_path
            if not os.access(path, os.W_OK):
                self.msg = "No write permission to this directory"
                return
            # Auto-create playlist subfolder
            if self.playlist_name:
                folder_name = sanitize_filename(self.playlist_name)
                pl_path = os.path.join(path, folder_name)
                try:
                    os.makedirs(pl_path, exist_ok=True)
                    path = pl_path
                except OSError as e:
                    self.msg = f"Failed to create playlist folder: {e}"
                    return
            self.app.config["last_dir"] = path
            self.app.pop_screen()
            self.app.pop_screen()
            if self.playlist_videos:
                self.app.push_screen(
                    PlaylistProgress(
                        self.app, self.playlist_videos, self.fmt["id"], path,
                        playlist_title=self.playlist_title,
                        mp3_mode=self.mp3_mode,
                        fmt_acodec=self.fmt.get("acodec", "")
                    )
                )
            else:
                self.app.push_screen(
                    DownloadProgress(
                        self.app, self.url, self.fmt, self.video_title, path
                    )
                )


class DownloadProgress(Screen):
    def __init__(self, app, url, fmt, video_title, dest_dir):
        super().__init__(app)
        self.url = url
        self.fmt = fmt
        self.video_title = video_title
        self.dest_dir = dest_dir
        self.percent = 0
        self.speed = ""
        self.eta = ""
        self.total_size = ""
        self.downloaded = ""
        self.fragment_index = ""
        self.fragment_count = ""
        self.filename = ""
        self.status = "starting"
        self.error = ""
        self.proc = None
        self.stream_count = 1
        self.last_pct_val = 0.0
        self._start()

    def _start(self):
        fmt_id = self.fmt["id"]
        # Auto-merge: jika video-only (acodec=none), gabung dengan audio terbaik
        if self.fmt.get("acodec", "") == "none":
            fmt_id = f"{fmt_id}+bestaudio/best"
        def run():
            try:
                tmpl = "ytui:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s|%(progress.downloaded_bytes)s|%(progress.fragment_index)s|%(progress.fragment_count)s"
                cmd = [
                    "yt-dlp",
                    "-f", fmt_id,
                    "--newline",
                    "--progress-template", tmpl,
                    "-o", os.path.join(self.dest_dir, "%(title)s.%(ext)s"),
                    self.url,
                ]
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"}
                )
                for line in self.proc.stdout:
                    line = line.strip()
                    if line.startswith("ytui:"):
                        parts = line[5:].split("|")
                        if len(parts) >= 5:
                            self.percent = parts[0].strip()
                            self.speed = parts[1].strip()
                            self.eta = parts[2].strip()
                            self.total_size = parts[3].strip()
                            self.downloaded = parts[4].strip()
                            self.fragment_index = parts[5].strip() if len(parts) >= 6 else ""
                            self.fragment_count = parts[6].strip() if len(parts) >= 7 else ""
                            self.status = "downloading"
                    elif "[Merger]" in line:
                        self.status = "merging"
                    elif "[ExtractAudio]" in line:
                        self.status = "processing audio"
                    elif "[Metadata]" in line:
                        self.status = "writing metadata"
                    elif "has already been" in line and "download" in line:
                        self.status = "done"
                        self.percent = "100"
                    elif "ERROR:" in line:
                        self.error = line
                        self.status = "error"
                    elif line and not line.startswith("["):
                        self.filename = line[:80]
                if self.proc.wait() == 0 and self.status != "error":
                    self.status = "done"
                    self.percent = "100"
                    self.app.history.add(
                        self.url, self.video_title,
                        self.fmt["id"], self.fmt.get("note", ""),
                        self.dest_dir, "success"
                    )
                elif self.status != "error" and self.status != "cancelled":
                    self.status = "done"
            except FileNotFoundError:
                self.error = "yt-dlp not found!"
                self.status = "error"
            except Exception as e:
                self.error = str(e)
                self.status = "error"
        threading.Thread(target=run, daemon=True).start()

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Downloading...")

        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            title = self.video_title[:w - 4]
            self.app.stdscr.addstr(3, 2, title)
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        except curses.error:
            pass

        y = 6
        bar_w = min(50, w - 10)

        if self.status == "error":
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
                self.app.stdscr.addstr(y, 2, f" ERROR: {self.error[:w-10]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
            except curses.error:
                pass
            self.draw_status("Esc to go back")
            return

        if self.status == "starting":
            try:
                self.app.stdscr.addstr(y, 2, " Starting download...")
            except curses.error:
                pass
            self.draw_status("Please wait...")
            return

        if self.status == "done":
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_PROGRESS) | curses.A_BOLD)
                self.app.stdscr.addstr(y, 2, " ✓ Download complete!")
                self.app.stdscr.attroff(curses.color_pair(COLOR_PROGRESS) | curses.A_BOLD)
                self.app.stdscr.addstr(y + 2, 2, f" Saved to: {self.dest_dir}")
            except curses.error:
                pass
            self.app.stdscr.addstr(h - 4, 2, " Esc to go back")
            return

        # 1. Fragment-based (HLS priority)
        pct = None
        if self.fragment_count and self.fragment_count not in ("NA", "", "0"):
            try:
                fi = float(self.fragment_index) if self.fragment_index and self.fragment_index not in ("NA", "") else 0
                fc = float(self.fragment_count)
                if fc > 0:
                    pct = (fi / fc) * 100
            except (ValueError, TypeError):
                pass

        # 2. Fallback: percent string dari yt-dlp (progressive format)
        if pct is None:
            pct_raw = self.percent.strip().rstrip("%").strip() if self.percent else ""
            if pct_raw and pct_raw not in ("NA", "N/A", ""):
                try:
                    pct = float(pct_raw)
                except ValueError:
                    pass

        if pct is not None:
            filled = int(bar_w * pct / 100)
            bar = "█" * filled + "░" * (bar_w - filled)
            pct_str = f"{pct:.1f}%"
        else:
            bar = "░" * bar_w
            pct_str = "?%"

        # Deteksi reset stream (auto-merge: video-only + audio)
        if pct is not None and self.last_pct_val > 50 and pct < 10:
            self.stream_count += 1
        if pct is not None:
            self.last_pct_val = pct

        try:
            self.app.stdscr.addstr(y, 2, f" {pct_str}  [{bar}]")
            y += 1
            info_parts = []
            if self.downloaded and self.downloaded not in ("NA", "N/A", "0"):
                d = fmt_filesize(self.downloaded)
                if self.total_size and self.total_size.strip() not in ("NA", "N/A", "0", ""):
                    info_parts.append(f"{d} / {self.total_size.strip()}")
                else:
                    info_parts.append(f"{d} downloaded")
            if self.speed and self.speed.strip() not in ("NA", "N/A", "0", ""):
                info_parts.append(f"Speed: {self.speed.strip()}")
            if self.eta and self.eta.strip() not in ("NA", "N/A", "Unknown", "0", "0:00", "00:00", ""):
                info_parts.append(f"ETA: {self.eta.strip()}")
            if info_parts:
                self.app.stdscr.addstr(y, 2, " " + "  •  ".join(info_parts))
            y += 1
            status_labels = {
                "downloading": f"Downloading stream {self.stream_count}" if self.stream_count > 1 else "Downloading",
                "merging": "Merging video & audio...",
                "processing audio": "Processing audio...",
                "writing metadata": "Writing metadata...",
            }
            label = status_labels.get(self.status, self.status)
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(y, 2, f" {label}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            y += 1
            if self.filename:
                self.app.stdscr.addstr(y, 2, f" {self.filename[:w-4]}")
        except curses.error:
            pass

        self.draw_status("q cancel download  Esc back when done")

    def handle_key(self, key):
        if key in (ord("q"), ord("Q")) and self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            self.status = "cancelled"
        elif key == 27:
            if self.status in ("done", "error", "cancelled"):
                self.app.pop_screen()


class HistoryView(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.idx = 0
        self.offset = 0
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Download History")

        entries = self.app.history.entries
        if not entries:
            try:
                self.app.stdscr.addstr(h // 2, 4, "No download history yet.")
            except curses.error:
                pass
            self.draw_status("Esc back")
            return

        header = f"{'#':>3}  {'Title':<40}  {'Fmt':<6}  {'Date':<12}"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
            self.app.stdscr.addstr(2, 0, header[: w - 1])
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        max_visible = h - 6
        if self.idx < self.offset:
            self.offset = self.idx
        if self.idx >= self.offset + max_visible:
            self.offset = self.idx - max_visible + 1

        for i, entry in enumerate(entries[self.offset:self.offset + max_visible]):
            y = 3 + i
            title = entry.get("title", "?")[:38]
            fmt_id = entry.get("format_id", "?")
            date = fmt_time(entry.get("timestamp", ""))
            line = f"{self.offset + i + 1:>3}  {title:<40}  {fmt_id:<6}  {date:<12}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if (self.offset + i) == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 0, line[: w - 1])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        if self.msg:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.app.stdscr.addstr(h - 4, 2, f" {self.msg[:w-4]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except curses.error:
                pass

        stats = f"Total: {len(entries)} downloads"
        self.draw_status(f"{stats}  ↑/↓ navigate  r redownload  d delete  C clear  Esc back")

    def handle_key(self, key):
        entries = self.app.history.entries
        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(len(entries) - 1, self.idx + 1)
        elif key in (ord("r"), ord("R")) and entries:
            entry = entries[self.idx]
            url = entry.get("url", "")
            if url:
                self.app.push_screen(FormatSelector(self.app, url))
        elif key in (ord("d"), ord("D")) and entries:
            self.app.history.delete(self.idx)
            self.idx = min(self.idx, len(self.app.history.entries) - 1)
            self.msg = "Entry deleted"
        elif key == ord("C") and entries:
            self.app.history.clear()
            self.idx = 0
            self.msg = "History cleared"


class BatchDownload(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.file_path = ""
        self.urls = []
        self.idx = 0
        self.offset = 0
        self.mode = "select"  # select | file_input | confirm
        self.current_path = app.config["last_dir"]
        self.entries = []
        self.dir_idx = 0
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Batch Download")

        if self.mode == "select":
            try:
                self.app.stdscr.addstr(h // 2 - 1, 4, "Select a .txt file containing URLs (one per line):")
                self.app.stdscr.addstr(h // 2, 4, "[F] Browse files    [P] Paste file path    [Esc] Back")
            except curses.error:
                pass
            self.draw_status("F browse  P paste path  Esc back")
        elif self.mode == "dir":
            path_display = self.current_path[:w - 4]
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(2, 0, f" {path_display}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass
            max_visible = h - 6
            if self.dir_idx < self.offset:
                self.offset = self.dir_idx
            if self.dir_idx >= self.offset + max_visible:
                self.offset = self.dir_idx - max_visible + 1
            for i, entry in enumerate(self.entries[self.offset:self.offset + max_visible]):
                y = 4 + i
                display = entry if entry != ".." else "[..] Parent Directory"
                attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if (self.offset + i) == self.dir_idx else curses.color_pair(COLOR_MENU)
                try:
                    self.app.stdscr.attron(attr)
                    self.app.stdscr.addstr(y, 2, f"{'>' if (self.offset+i)==self.dir_idx else ' '} {display:<{w-8}}")
                    self.app.stdscr.attroff(attr)
                except curses.error:
                    pass
            self.draw_status("↑/↓ navigate  Enter open dir  d select file  Esc back")

        if self.msg:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.app.stdscr.addstr(h - 4, 2, f" {self.msg[:w-4]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except curses.error:
                pass

    def _browse_dir(self, path):
        self.current_path = path
        try:
            items = []
            for e in sorted(os.listdir(path)):
                full = os.path.join(path, e)
                if os.path.isdir(full) and not e.startswith("."):
                    items.append(("dir", e))
                elif e.endswith(".txt") and not e.startswith("."):
                    items.append(("file", e))
            self.entries = [("parent", "..")] + items
            self.dir_idx = 0
            self.offset = 0
        except PermissionError:
            self.entries = [("parent", "..")]
            self.msg = "Permission denied"
        except FileNotFoundError:
            self.entries = [("parent", "..")]
            self.msg = "Path not found"

    def handle_key(self, key):
        if key == 27:
            if self.mode == "dir":
                self.mode = "select"
            else:
                self.app.pop_screen()
        elif self.mode == "select":
            if key in (ord("f"), ord("F")):
                self.mode = "dir"
                self._browse_dir(self.current_path)
            elif key in (ord("p"), ord("P")):
                self.mode = "file_input"
        elif self.mode == "dir":
            if key == curses.KEY_UP:
                self.dir_idx = max(0, self.dir_idx - 1)
            elif key == curses.KEY_DOWN:
                self.dir_idx = min(len(self.entries) - 1, self.dir_idx + 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                etype, ename = self.entries[self.dir_idx]
                if etype == "parent":
                    new_path = os.path.dirname(self.current_path.rstrip("/"))
                    self._browse_dir(new_path)
                elif etype == "dir":
                    self._browse_dir(os.path.join(self.current_path, ename))
                elif etype == "file":
                    fpath = os.path.join(self.current_path, ename)
                    self._load_urls(fpath)
        elif self.mode == "file_input":
            if key in (curses.KEY_ENTER, 10, 13):
                self._load_urls(self.file_path)
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.file_path = self.file_path[:-1]
            elif 32 <= key < 127:
                self.file_path += chr(key)
                self.msg = ""

    def _load_urls(self, fpath):
        try:
            with open(fpath) as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            if not urls:
                self.msg = "No valid URLs found in file"
                return
            self.urls = urls
            self.mode = "confirm"
            self.app.push_screen(BatchConfirm(self.app, urls, fpath))
        except FileNotFoundError:
            self.msg = f"File not found: {fpath}"
        except Exception as e:
            self.msg = str(e)


class BatchConfirm(Screen):
    def __init__(self, app, urls, src_path):
        super().__init__(app)
        self.urls = urls
        self.src_path = src_path
        self.idx = 0

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Batch Download")

        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
            self.app.stdscr.addstr(2, 2, f" {len(self.urls)} URLs loaded from {os.path.basename(self.src_path)}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        max_visible = h - 7
        for i, url in enumerate(self.urls[:max_visible]):
            try:
                self.app.stdscr.addstr(4 + i, 2, f" {i + 1:>3}. {url[:w-10]}")
            except curses.error:
                pass

        if len(self.urls) > max_visible:
            try:
                self.app.stdscr.addstr(h - 5, 2, f" ... and {len(self.urls) - max_visible} more")
            except curses.error:
                pass

        options = [
            "[S] Select common format for all",
            "[D] Download all with best quality",
            "[Esc] Cancel",
        ]
        for i, opt in enumerate(options):
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(h // 2 + i, 4, f"  {opt:<50}")
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        self.draw_status("↑/↓ choose  Enter confirm  Esc cancel")

    def handle_key(self, key):
        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(2, self.idx + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.idx == 0:
                self.app.push_screen(BatchFormatPick(self.app, self.urls))
            elif self.idx == 1:
                self._download_all("best")
            elif self.idx == 2:
                self.app.pop_screen()

    def _download_all(self, fmt_id):
        self.app.pop_screen()
        self.app.push_screen(BatchProgress(self.app, self.urls, fmt_id))


class BatchFormatPick(Screen):
    def __init__(self, app, urls):
        super().__init__(app)
        self.urls = urls
        self.input_fmt = ""
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Select Format for Batch")

        lines = [
            "Enter yt-dlp format string (e.g.: 22, 18, best, 137+140, bv*+ba):",
            "",
            f"> {self.input_fmt}█",
            "",
            "Common formats:",
            "  18    = 640x360 mp4 (best for most phones)",
            "  22    = 1280x720 mp4",
            "  137+140 = 1080p video + m4a audio",
            "  bv*+ba = Best video + best audio (merge)",
        ]
        if self.msg:
            lines.append("")
            lines.append(self.msg)

        for i, line in enumerate(lines):
            attr = curses.color_pair(COLOR_ERROR) if self.msg and i == len(lines) - 1 else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(4 + i, 4, line[: w - 8])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        self.draw_status("Enter confirm  Esc cancel")

    def handle_key(self, key):
        if key == 27:
            self.app.pop_screen()
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.input_fmt.strip():
                self.app.pop_screen()
                self.app.pop_screen()
                self.app.push_screen(BatchProgress(self.app, self.urls, self.input_fmt.strip()))
            else:
                self.msg = "Format cannot be empty!"
        elif key == curses.KEY_BACKSPACE or key == 127:
            self.input_fmt = self.input_fmt[:-1]
            self.msg = ""
        elif 32 <= key < 127:
            self.input_fmt += chr(key)
            self.msg = ""


class BatchProgress(Screen):
    def __init__(self, app, urls, fmt_id):
        super().__init__(app)
        self.urls = urls
        self.fmt_id = fmt_id
        self.current = 0
        self.total = len(urls)
        self.results = []
        self.running = True
        self._start()

    def _start(self):
        def run():
            dest = self.app.config["last_dir"]
            for i, url in enumerate(self.urls):
                if not self.running:
                    break
                self.current = i
                try:
                    result = subprocess.run(
                        ["yt-dlp", "-f", self.fmt_id, "--newline",
                         "-o", os.path.join(dest, "%(title)s.%(ext)s"),
                         url],
                        capture_output=True, text=True, timeout=300
                    )
                    if result.returncode == 0:
                        self.results.append(("ok", url))
                    else:
                        err = result.stderr.strip()[:60]
                        self.results.append(("fail", url, err))
                except subprocess.TimeoutExpired:
                    self.results.append(("fail", url, "Timeout"))
                except Exception as e:
                    self.results.append(("fail", url, str(e)[:60]))
            self.current = self.total
        threading.Thread(target=run, daemon=True).start()

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Batch Download Progress")

        try:
            self.app.stdscr.addstr(3, 2, f" Progress: {self.current}/{self.total}")
            if self.total > 0:
                pct = int(self.current / self.total * 100)
                bar_w = 40
                filled = int(bar_w * pct / 100)
                bar = "█" * filled + "░" * (bar_w - filled)
                self.app.stdscr.addstr(4, 2, f" [{bar}] {pct}%")
        except curses.error:
            pass

        max_show = min(len(self.results), h - 9)
        for i, r in enumerate(self.results[:max_show]):
            url_short = r[1][:50]
            if r[0] == "ok":
                icon = "✓"
                attr = curses.color_pair(COLOR_PROGRESS)
            else:
                icon = "✗"
                attr = curses.color_pair(COLOR_ERROR)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(6 + i, 2, f" {icon} {url_short}")
                self.app.stdscr.attroff(attr)
                if r[0] == "fail" and len(r) > 2:
                    self.app.stdscr.addstr(6 + i, w // 2, f" {r[2]}")
            except curses.error:
                pass

        if self.current >= self.total:
            ok_count = sum(1 for r in self.results if r[0] == "ok")
            fail_count = sum(1 for r in self.results if r[0] == "fail")
            summary = f" Complete: {ok_count} OK, {fail_count} failed"
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
                self.app.stdscr.addstr(h - 5, 2, summary)
                self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            except curses.error:
                pass

        self.draw_status("Esc back when done")

    def handle_key(self, key):
        if key == 27 and self.current >= self.total:
            self.app.pop_screen()
        elif key == 27 and self.current < self.total:
            self.running = False
            self.current = self.total
        elif key == ord("q"):
            self.running = False
            self.current = self.total


# ═══════════════════════════════════════════════════
# Playlist screens
# ═══════════════════════════════════════════════════

class PlaylistDetect(Screen):
    """Screen sementara: deteksi apakah URL adalah playlist, redirect sesuai hasil."""
    def __init__(self, app, url):
        super().__init__(app)
        self.url = url
        self.loading = True
        self.redirected = False
        self.error = ""
        self.is_playlist = False
        self.playlist_data = None
        self._check()

    def _check(self):
        def run():
            try:
                result = subprocess.run(
                    ["yt-dlp", "--flat-playlist", "--dump-json", self.url],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    self.error = result.stderr.strip()[:100]
                    self.loading = False
                    return
                lines = [l for l in result.stdout.strip().split('\n') if l]
                if not lines:
                    self.error = "No data returned"
                    self.loading = False
                    return
                first = json.loads(lines[0])
                count = first.get('playlist_count', 0) or len(lines)
                if count > 1:
                    self.is_playlist = True
                    videos = []
                    for line in lines:
                        d = json.loads(line)
                        vid_url = d.get('original_url') or d.get('webpage_url') or \
                                   f"https://youtube.com/watch?v={d.get('id', '')}"
                        videos.append({
                            'id': d.get('id', ''),
                            'title': d.get('title', '?'),
                            'duration': d.get('duration', 0),
                            'url': vid_url,
                        })
                    self.playlist_data = {
                        'title': first.get('playlist_title', first.get('playlist', 'Playlist')),
                        'uploader': first.get('playlist_uploader') or first.get('channel') or first.get('uploader', ''),
                        'count': count,
                        'videos': videos,
                    }
                else:
                    self.is_playlist = False
            except json.JSONDecodeError:
                self.error = "Failed to parse response"
            except subprocess.TimeoutExpired:
                self.error = "Request timed out"
            except Exception as e:
                self.error = str(e)[:100]
            self.loading = False
        threading.Thread(target=run, daemon=True).start()

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Checking URL...")
        if self.loading:
            try:
                msg = " Fetching video info... "
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
                self.app.stdscr.addstr(h // 2, w // 2 - len(msg) // 2, msg)
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO) | curses.A_BOLD)
            except curses.error:
                pass
            self.draw_status("Please wait...  Esc cancel")
            return
        if self.error:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
                self.app.stdscr.addstr(h // 2 - 1, 4, f" Error: {self.error[:w-10]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR) | curses.A_BOLD)
                self.app.stdscr.addstr(h // 2 + 1, 4, " Press Esc to go back")
            except curses.error:
                pass
            self.draw_status("Esc back")
            return
        # Redirect on next frame
        if not self.redirected:
            self.redirected = True
            self.app.pop_screen()
            if self.is_playlist:
                self.app.push_screen(PlaylistOverview(self.app, self.playlist_data))
            else:
                self.app.push_screen(FormatSelector(self.app, self.url))

    def handle_key(self, key):
        if self.loading and key == 27:
            self.loading = False
            self.redirected = True
            self.app.pop_screen()
        elif not self.loading and key == 27:
            self.app.pop_screen()


class PlaylistOverview(Screen):
    """Info playlist + pilihan: Download All, Select Videos, Range."""
    def __init__(self, app, pl_data):
        super().__init__(app)
        self.pl_data = pl_data
        self.idx = 0
        self.options = [
            ("Download All Videos", "all"),
            ("Select Videos (multi-select)", "select"),
            ("Download Range (e.g. 1,3,5-10)", "range"),
        ]
        self.range_input = ""
        self.range_mode = False
        self.mp3_mode = False
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Playlist Detected")

        d = self.pl_data
        title = d.get('title', 'Playlist')[:w-6]
        uploader = d.get('uploader', '')[:30]
        count = d.get('count', 0)
        total_dur = sum(v.get('duration', 0) for v in d.get('videos', []))
        hours, rem = divmod(total_dur, 3600)
        mins, secs = divmod(rem, 60)
        dur_str = f"{hours}h {mins}m" if hours else f"{mins}m {secs}s"

        info_lines = [
            f"  {title}",
            f"  Channel: {uploader}" if uploader else "",
            f"  Videos: {count}  |  Total duration: {dur_str}",
        ]
        for i, line in enumerate(info_lines):
            if line:
                try:
                    attr = curses.color_pair(COLOR_TITLE) | curses.A_BOLD if i == 0 else curses.color_pair(COLOR_INFO)
                    self.app.stdscr.attron(attr)
                    self.app.stdscr.addstr(3 + i, 0, line[:w-1])
                    self.app.stdscr.attroff(attr)
                except curses.error:
                    pass

        # MP3 mode indicator
        mp3_tag = "🎵 MP3 Mode: ON  (audio only)" if self.mp3_mode else "🎵 MP3 Mode: OFF"
        try:
            attr = curses.color_pair(COLOR_PROGRESS) if self.mp3_mode else curses.color_pair(COLOR_MENU)
            self.app.stdscr.attron(attr)
            self.app.stdscr.addstr(6, 4, f" [M] {mp3_tag:<40}")
            self.app.stdscr.attroff(attr)
        except curses.error:
            pass

        y_start = 8
        for i, (label, _) in enumerate(self.options):
            y = y_start + i
            prefix = " >" if i == self.idx and not self.range_mode else "  "
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.idx and not self.range_mode else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 4, f"{prefix} {label:<45}")
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        if self.range_mode:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(y_start + 4, 4, f" Enter range: {self.range_input}█")
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass

        if self.msg:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.app.stdscr.addstr(y_start + 5, 4, f" {self.msg[:w-8]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except curses.error:
                pass

        status = "Enter range, Enter confirm, Esc cancel" if self.range_mode else "↑/↓ choose  Enter select  [M] MP3 toggle  Esc back"
        self.draw_status(status)

    def handle_key(self, key):
        if self.range_mode:
            if key == 27:
                self.range_mode = False
                self.range_input = ""
            elif key in (curses.KEY_ENTER, 10, 13):
                self._start_range_download()
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.range_input = self.range_input[:-1]
            elif 32 <= key < 127:
                self.range_input += chr(key)
            return

        if key == 27:
            self.app.pop_screen()
        elif key in (ord('m'), ord('M')):
            self.mp3_mode = not self.mp3_mode
        elif key == curses.KEY_UP:
            self.idx = (self.idx - 1) % len(self.options)
        elif key == curses.KEY_DOWN:
            self.idx = (self.idx + 1) % len(self.options)
        elif key in (curses.KEY_ENTER, 10, 13):
            action = self.options[self.idx][1]
            if action == "all":
                self._proceed(self.pl_data['videos'])
            elif action == "select":
                self.app.push_screen(PlaylistSelector(self.app, self.pl_data, mp3_mode=self.mp3_mode))
            elif action == "range":
                self.range_mode = True
                self.range_input = ""

    def _parse_range(self, text, max_val):
        """Parse '1,3,5-10' jadi list index 0-based."""
        indices = set()
        for part in text.replace(' ', '').split(','):
            if not part:
                continue
            if '-' in part:
                try:
                    a, b = part.split('-', 1)
                    start, end = int(a), int(b)
                    indices.update(range(max(1, start), min(max_val, end) + 1))
                except ValueError:
                    return None
            else:
                try:
                    indices.add(int(part))
                except ValueError:
                    return None
        return sorted(i - 1 for i in indices if 1 <= i <= max_val)

    def _start_range_download(self):
        max_v = self.pl_data['count']
        selected = self._parse_range(self.range_input, max_v)
        if selected is None or not selected:
            self.msg = f"Invalid range. Use format like: 1,3,5-10 (1-{max_v})"
            return
        videos = [self.pl_data['videos'][i] for i in selected if 0 <= i < len(self.pl_data['videos'])]
        self._proceed(videos)

    def _proceed(self, videos):
        first_url = videos[0]['url']
        if self.mp3_mode:
            # Langsung ke FolderBrowser + PlaylistProgress dengan MP3
            dummy_fmt = {"id": "bestaudio", "acodec": "mp3", "ext": "mp3"}
            pl_title = self.pl_data['title']
            self.app.push_screen(
                FolderBrowser(self.app, first_url, dummy_fmt,
                              f"[MP3] {pl_title[:35]}",
                              playlist_name=pl_title,
                              playlist_videos=videos,
                              playlist_title=pl_title,
                              mp3_mode=True)
            )
        else:
            self.app.push_screen(
                FormatSelector(self.app, first_url, playlist_videos=videos,
                               playlist_title=self.pl_data['title'])
            )


class PlaylistSelector(Screen):
    """Multi-select video list dengan checkbox."""
    def __init__(self, app, pl_data, mp3_mode=False):
        super().__init__(app)
        self.pl_data = pl_data
        self.mp3_mode = mp3_mode
        self.videos = pl_data.get('videos', [])
        self.selected = [True] * len(self.videos)  # default: all selected
        self.idx = 0
        self.offset = 0
        self.msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Select Videos")

        pl_title = self.pl_data.get('title', 'Playlist')[:w-6]
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(2, 0, f" {pl_title}")
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        header = f" {'':3}  {'Title':<50}  {'Dur':<6}"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
            self.app.stdscr.addstr(3, 0, header[:w-1])
            self.app.stdscr.attroff(curses.color_pair(COLOR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        max_visible = h - 7
        if self.idx < self.offset:
            self.offset = self.idx
        if self.idx >= self.offset + max_visible:
            self.offset = self.idx - max_visible + 1

        for i, v in enumerate(self.videos[self.offset:self.offset + max_visible]):
            y = 4 + i
            sel = self.selected[self.offset + i]
            checkbox = "[x]" if sel else "[ ]"
            title = v.get('title', '?')[:48]
            dur = v.get('duration', 0)
            mins, secs = divmod(int(dur), 60)
            dur_str = f"{mins}:{secs:02d}" if dur else "?:??"
            line = f" {checkbox}  {title:<50}  {dur_str:<6}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if (self.offset + i) == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 0, line[:w-1])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        sel_count = sum(self.selected)
        try:
            status_info = f" {sel_count}/{len(self.videos)} selected"
            self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
            self.app.stdscr.addstr(h - 4, 2, status_info[:w-4])
            self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
        except curses.error:
            pass

        if self.msg:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_ERROR))
                self.app.stdscr.addstr(h - 5, 2, f" {self.msg[:w-4]}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_ERROR))
            except curses.error:
                pass

        self.draw_status("↑/↓ navigate  Space toggle  a all  n none  d download  Esc back")

    def handle_key(self, key):
        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = max(0, self.idx - 1)
        elif key == curses.KEY_DOWN:
            self.idx = min(len(self.videos) - 1, self.idx + 1)
        elif key == ord(' '):
            self.selected[self.idx] = not self.selected[self.idx]
        elif key in (ord('a'), ord('A')):
            all_sel = all(self.selected)
            for i in range(len(self.selected)):
                self.selected[i] = not all_sel
        elif key in (ord('n'), ord('N')):
            for i in range(len(self.selected)):
                self.selected[i] = False
        elif key in (ord('d'), ord('D')):
            selected_videos = [v for i, v in enumerate(self.videos) if self.selected[i]]
            if not selected_videos:
                self.msg = "No videos selected!"
                return
            self.app.pop_screen()  # balik ke PlaylistOverview
            self.app.pop_screen()  # PlaylistOverview juga di-pop
            first_url = selected_videos[0]['url']
            if self.mp3_mode:
                dummy_fmt = {"id": "bestaudio", "acodec": "mp3", "ext": "mp3"}
                self.app.push_screen(
                    FolderBrowser(self.app, first_url, dummy_fmt,
                                  f"[MP3] {self.pl_data['title'][:35]}",
                                  playlist_name=self.pl_data['title'],
                                  playlist_videos=selected_videos,
                                  playlist_title=self.pl_data['title'],
                                  mp3_mode=True)
                )
            else:
                self.app.push_screen(
                    FormatSelector(self.app, first_url, playlist_videos=selected_videos,
                                   playlist_title=self.pl_data['title'])
                )


class PlaylistProgress(Screen):
    """Download sequential playlist dengan progress per-video."""
    def __init__(self, app, videos, fmt_id, dest_dir, playlist_title="",
                 mp3_mode=False, fmt_acodec=""):
        super().__init__(app)
        self.videos = videos
        self.fmt_id = fmt_id
        self.mp3_mode = mp3_mode
        self.fmt_acodec = fmt_acodec
        self.dest_dir = dest_dir
        self.playlist_title = playlist_title
        self.current = 0
        self.total = len(videos)
        self.results = []  # (ok/fail, title, error?)
        self.running = True
        self.current_title = ""
        self.current_percent = 0
        self.current_speed = ""
        self.current_eta = ""
        self.current_status = "waiting"
        self.current_stream = 1
        self.last_stream_pct = 0.0
        self.proc = None
        self._start_next()

    def _start_next(self):
        if self.current >= self.total or not self.running:
            return
        v = self.videos[self.current]
        url = v['url']
        self.current_title = v.get('title', '?')[:60]
        self.current_percent = 0
        self.current_speed = ""
        self.current_eta = ""
        self.current_status = "starting"
        self.current_stream = 1
        self.last_stream_pct = 0.0
        self._download_one(url)

    def _download_one(self, url):
        def run():
            try:
                tmpl = "ytui:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s|%(progress.downloaded_bytes)s|%(progress.fragment_index)s|%(progress.fragment_count)s"
                if self.mp3_mode:
                    cmd = [
                        "yt-dlp",
                        "-x", "--audio-format", "mp3",
                        "-f", "bestaudio/best",
                        "--newline",
                        "--progress-template", tmpl,
                        "-o", os.path.join(self.dest_dir, "%(title)s.%(ext)s"),
                        url,
                    ]
                else:
                    fmt_id = self.fmt_id
                    if self.fmt_acodec == "none":
                        fmt_id = f"{fmt_id}+bestaudio/best"
                    cmd = [
                        "yt-dlp",
                        "-f", fmt_id,
                        "--newline",
                        "--progress-template", tmpl,
                        "-o", os.path.join(self.dest_dir, "%(title)s.%(ext)s"),
                        url,
                    ]
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"}
                )
                for line in self.proc.stdout:
                    line = line.strip()
                    if line.startswith("ytui:"):
                        parts = line[5:].split("|")
                        if len(parts) >= 5:
                            # 1. Fragment-based (HLS priority)
                            pct = None
                            fi_s = parts[5].strip() if len(parts) >= 6 else ""
                            fc_s = parts[6].strip() if len(parts) >= 7 else ""
                            if fc_s and fc_s not in ("NA", "", "0"):
                                try:
                                    fi = float(fi_s) if fi_s and fi_s not in ("NA", "") else 0
                                    fc = float(fc_s)
                                    if fc > 0:
                                        pct = (fi / fc) * 100
                                except ValueError:
                                    pass
                            # 2. Fallback: percent string
                            if pct is None:
                                pct_raw = parts[0].strip().rstrip("%").strip()
                                if pct_raw and pct_raw not in ("NA", "N/A", ""):
                                    try:
                                        pct = float(pct_raw)
                                    except ValueError:
                                        pass
                            self.current_percent = pct or 0
                            # Deteksi reset stream (auto-merge)
                            if self.last_stream_pct > 50 and (pct or 0) < 10:
                                self.current_stream += 1
                            if pct is not None:
                                self.last_stream_pct = pct
                            self.current_speed = parts[1].strip()
                            self.current_eta = parts[2].strip()
                            self.current_status = "downloading"
                    elif "[Merger]" in line:
                        self.current_status = "merging"
                    elif "ERROR:" in line:
                        self.current_status = "error"
                ret = self.proc.wait()
                if ret == 0:
                    self.results.append(("ok", self.current_title, ""))
                else:
                    self.results.append(("fail", self.current_title, f"exit={ret}"))
            except Exception as e:
                self.results.append(("fail", self.current_title, str(e)[:40]))
            finally:
                self.current += 1
                if self.running:
                    self._start_next()
        threading.Thread(target=run, daemon=True).start()

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Playlist Download")

        # Overall progress
        bar_w = min(40, w - 10)
        overall_pct = (self.current / self.total * 100) if self.total > 0 else 0
        filled = int(bar_w * overall_pct / 100)
        o_bar = "█" * filled + "░" * (bar_w - filled)
        try:
            self.app.stdscr.addstr(3, 2, f" Playlist: {self.current}/{self.total}  [{o_bar}]  {overall_pct:.0f}%")
        except curses.error:
            pass

        pl_name = self.playlist_title[:w-10] if self.playlist_title else ""
        mode_tag = " [MP3]" if self.mp3_mode else ""
        if pl_name:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(4, 2, f" {pl_name}{mode_tag}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass

        # Current video
        if self.current < self.total:
            v = self.videos[self.current]
            title = v.get('title', '?')[:w-6]
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
                self.app.stdscr.addstr(6, 2, f" Now: {title}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            except curses.error:
                pass

            # Inner progress bar
            inner_filled = int(bar_w * self.current_percent / 100)
            i_bar = "█" * inner_filled + "░" * (bar_w - inner_filled)
            try:
                self.app.stdscr.addstr(7, 2, f" [{i_bar}]  {self.current_percent:.1f}%")
            except curses.error:
                pass

            # Info line
            info = []
            if self.current_speed and self.current_speed.strip() not in ("NA","N/A","0",""):
                info.append(f"Speed: {self.current_speed.strip()}")
            if self.current_eta and self.current_eta.strip() not in ("NA","N/A","0","0:00","00:00","Unknown",""):
                info.append(f"ETA: {self.current_eta.strip()}")
            if info:
                try:
                    self.app.stdscr.addstr(8, 2, " " + "  •  ".join(info))
                except curses.error:
                    pass

            status_label = {
                "starting": "Starting...",
                "downloading": f"Downloading stream {self.current_stream}" if self.current_stream > 1 else "Downloading",
                "merging": "Merging...",
                "error": "Error!",
            }.get(self.current_status, self.current_status)
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(9, 2, f" {status_label}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass

        # Results
        y = 11
        ok_count = sum(1 for r in self.results if r[0] == "ok")
        fail_count = sum(1 for r in self.results if r[0] == "fail")
        for i, r in enumerate(self.results[-(h - y - 2):]):  # show latest results
            icon = "✓" if r[0] == "ok" else "✗"
            title_short = r[1][:w - 12]
            attr = curses.color_pair(COLOR_PROGRESS) if r[0] == "ok" else curses.color_pair(COLOR_ERROR)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y + i, 2, f" {icon} {title_short}")
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        if self.current >= self.total:
            summary = f" Complete: {ok_count} OK, {fail_count} failed"
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
                self.app.stdscr.addstr(h - 5, 2, summary[:w-4])
                self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            except curses.error:
                pass

        self.draw_status("q cancel  Esc back when done")

    def handle_key(self, key):
        if key in (ord("q"), ord("Q")) and self.current < self.total:
            self.running = False
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
            self.current = self.total
        elif key == 27 and self.current >= self.total:
            self.app.pop_screen()


class SettingsView(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.fields = [
            ("last_dir", "Default Download Directory", "path"),
            ("default_format", "Default Format String", "text"),
            ("max_history", "Max History Entries", "int"),
            ("theme", "Color Theme", "choice", ["dark", "light"]),
        ]
        self.idx = 0
        self.edit_mode = False
        self.edit_value = ""
        self.edit_field = ""
        self.msg = ""
        self.success_msg = ""

    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Settings")

        for i, field in enumerate(self.fields):
            key, label = field[0], field[1]
            ftype = field[2] if len(field) > 2 else "text"
            val = str(self.app.config[key])
            if ftype == "choice":
                choices = field[3] if len(field) > 3 else []
                # Show with < > brackets for toggle indicator
                display = f" {label:<35}  <{val:^8}>  [Enter to toggle]"
            else:
                display = f" {label:<35} {val:<40}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.idx and not self.edit_mode else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(4 + i * 2, 2, display[: w - 4])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        if self.edit_mode:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_INFO))
                self.app.stdscr.addstr(h - 5, 2, f" Edit: {self.edit_field} = {self.edit_value}█")
                self.app.stdscr.attroff(curses.color_pair(COLOR_INFO))
            except curses.error:
                pass

        if self.success_msg:
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_PROGRESS))
                self.app.stdscr.addstr(h - 6, 2, f" {self.success_msg}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_PROGRESS))
            except curses.error:
                pass

        status = "Editing..." if self.edit_mode else "↑/↓ navigate  Enter edit  Enter=toggle on choice  Ctrl+T quick toggle  Esc back"
        self.draw_status(status)

    def handle_key(self, key):
        if self.edit_mode:
            if key == 27:
                self.edit_mode = False
                self.msg = ""
            elif key in (curses.KEY_ENTER, 10, 13):
                key_name = self.fields[self.idx][0]
                ftype = self.fields[self.idx][2]
                if ftype == "int":
                    try:
                        val = int(self.edit_value)
                        if val <= 0:
                            self.msg = "Must be positive"
                            return
                        self.app.config[key_name] = val
                    except ValueError:
                        self.msg = "Invalid number"
                        return
                else:
                    self.app.config[key_name] = self.edit_value
                self.app.config.save()
                self.edit_mode = False
                self.success_msg = f" ✓ {self.fields[self.idx][1]} saved"
                self.msg = ""
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.edit_value = self.edit_value[:-1]
            elif 32 <= key < 127:
                self.edit_value += chr(key)
            return

        if key == 27:
            self.app.pop_screen()
        elif key == curses.KEY_UP:
            self.idx = (self.idx - 1) % len(self.fields)
        elif key == curses.KEY_DOWN:
            self.idx = (self.idx + 1) % len(self.fields)
        elif key in (curses.KEY_ENTER, 10, 13):
            key_name = self.fields[self.idx][0]
            ftype = self.fields[self.idx][2] if len(self.fields[self.idx]) > 2 else "text"
            if ftype == "choice":
                # Toggle theme directly
                self.app.toggle_theme()
                self.success_msg = f" ✓ Theme: {self.app.config['theme']}"
            else:
                self.edit_field = self.fields[self.idx][1]
                self.edit_value = str(self.app.config[key_name])
                self.edit_mode = True


class HelpScreen(Screen):
    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()
        self.draw_title("Help — Keyboard Shortcuts")

        sections = [
            ("Navigation", [
                ("\u2191 / \u2193", "Navigate up/down"),
                ("Enter", "Confirm / Select"),
                ("Esc", "Go back / Cancel"),
                ("?", "Show this help"),
            ]),
            ("Download", [
                ("d", "Download selected"),
                ("m", "Toggle MP3 mode"),
                ("Space", "Toggle selection"),
                ("q", "Quit / Cancel"),
            ]),
            ("Editing", [
                ("Backspace", "Delete character"),
                ("Ctrl+U", "Clear input"),
                ("Ctrl+V", "Paste from clipboard"),
            ]),
            ("General", [
                ("t", "Toggle dark/light theme"),
                ("a / n", "Select all / none"),
            ]),
        ]

        col_width = max(w // 4, 18)
        for col_idx, (title, items) in enumerate(sections):
            x = 2 + col_idx * col_width
            if x >= w - 10:
                break
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
                self.app.stdscr.addstr(3, x, f" {title}")
                self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            except curses.error:
                pass
            for i, (key, desc) in enumerate(items):
                row = 5 + i * 2
                if row >= h - 2:
                    break
                try:
                    self.app.stdscr.attron(curses.color_pair(COLOR_SEL) | curses.A_BOLD)
                    self.app.stdscr.addstr(row, x, f" {key:<15}")
                    self.app.stdscr.attroff(curses.color_pair(COLOR_SEL) | curses.A_BOLD)
                    self.app.stdscr.attron(curses.color_pair(COLOR_MENU))
                    self.app.stdscr.addstr(row, x + 16, desc[:w - x - 20])
                    self.app.stdscr.attroff(curses.color_pair(COLOR_MENU))
                except curses.error:
                    pass

        self.draw_status("Press any key to close help")

    def handle_key(self, key):
        self.app.pop_screen()


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.config = ConfigManager()
        self.history = HistoryManager(self.config)
        self.screens = []
        self.running = True
        self.start_url = None
        self._init_curses()
        self.push_screen(MainMenu(self))
        self._detect_clipboard()

    def _detect_clipboard(self):
        clipboard = shutil.which("termux-clipboard-get")
        if not clipboard:
            return
        try:
            content = subprocess.check_output([clipboard], timeout=2).decode().strip()
            if content and ("youtube.com" in content or "youtu.be" in content):
                self.start_url = content
        except Exception:
            pass

    def _init_curses(self):
        curses.use_default_colors()
        # Enable mouse tracking for clickable UI elements
        try:
            curses.mousemask(curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED)
        except curses.error:
            pass  # Terminal may not support mouse
        self.apply_theme(self.config["theme"])

    def apply_theme(self, theme_name="dark"):
        """Apply a named theme by re-initializing color pairs."""
        theme = THEMES.get(theme_name, THEME_DARK)
        for pair_num, color_key in COLOR_NAMES.items():
            fg, bg = theme.get(color_key, (curses.COLOR_WHITE, -1))
            try:
                curses.init_pair(pair_num, fg, bg)
            except curses.error:
                pass
        # Redraw current screen on next frame
        if self.screens:
            try:
                self.stdscr.clear()
                self.stdscr.refresh()
            except curses.error:
                pass

    def toggle_theme(self):
        """Switch between dark and light themes."""
        current = self.config["theme"]
        new_theme = "light" if current == "dark" else "dark"
        self.config["theme"] = new_theme
        self.apply_theme(new_theme)

    def push_screen(self, screen):
        self.screens.append(screen)

    def pop_screen(self):
        if len(self.screens) > 1:
            self.screens.pop()
        else:
            self.running = False

    def run(self):
        self.stdscr.timeout(100)  # 100ms timeout → ~10fps refresh tanpa perlu input
        while self.running:
            try:
                screen = self.screens[-1]
                screen.render()
                self.stdscr.refresh()
                key = self.stdscr.getch()
                if key != -1:  # -1 = timeout, tidak ada tombol ditekan
                    if key == ord("?"):
                        self.push_screen(HelpScreen(self))
                    elif key == curses.KEY_MOUSE:
                        screen.handle_mouse()
                    else:
                        screen.handle_key(key)
            except KeyboardInterrupt:
                self.running = False
            except curses.error:
                pass


def main():
    import shutil
    import sys
    if not shutil.which("yt-dlp"):
        print("ERROR: yt-dlp not found. Install it with:")
        print("  pip install yt-dlp")
        sys.exit(1)
    try:
        curses.wrapper(lambda stdscr: App(stdscr).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
