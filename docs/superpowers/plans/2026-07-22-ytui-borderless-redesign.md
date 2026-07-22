# YTUI Borderless & Theme Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all box-drawing borders from ytui and update light theme to modern minimal.

**Architecture:** All changes in single `ytui.py`. Theme dicts `THEME_DARK`/`THEME_LIGHT` updated at definition site. Screen render methods rewritten to eliminate box characters. `draw_dialog()` simplified to centered text.

**Tech Stack:** Python 3 + curses (stdlib only)

## Global Constraints

- Single file: `~/dev/video-downloader/ytui/ytui.py`
- No new dependencies
- Must work in Termux (Android) and standard terminals
- Config format unchanged

---

### Task 1: Update Light Theme

**Files:**
- Modify: `ytui.py:52-61` (THEME_LIGHT dict)

- [ ] **Step 1: Edit THEME_LIGHT**

Replace light theme with minimal palette (no COLORS, uses -1 default + A_BOLD/A_REVERSE/A_DIM at render time):

```
"menu":      (curses.COLOR_BLACK, -1)       (unchanged)
"title":     (curses.COLOR_BLACK, -1)       was COLOR_BLUE
"sel":       (-1, -1)                       was COLOR_WHITE on COLOR_BLUE
"status":    (curses.COLOR_WHITE, curses.COLOR_BLUE)  (unchanged)
"progress":  (curses.COLOR_GREEN, -1)       (unchanged)
"header":    (-1, -1)                       was COLOR_BLUE
"info":      (-1, -1)                       was COLOR_MAGENTA
"error":     (curses.COLOR_RED, -1)         (unchanged)
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('ytui.py').read()); print('OK')"`

---

### Task 2: Remove Dead `draw_button`

**Files:**
- Modify: `ytui.py:261-288` (delete entire method)

- [ ] **Step 1: Delete draw_button**

Remove lines 261-288 (the method including docstring and body).

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('ytui.py').read()); print('OK')"`

---

### Task 3: Borderless `draw_dialog`

**Files:**
- Modify: `ytui.py:347-372` (rewrite draw_dialog method)

**Interfaces:**
- Consumes: same signature `draw_dialog(self, title, message)` — no width param change needed (all callers pass 2 args)

- [ ] **Step 1: Rewrite draw_dialog**

Replace lines 347-372 with:

```python
    def draw_dialog(self, title, message):
        h, w = self.app.stdscr.getmaxyx()
        lines = message.split("\n")
        title_str = f"  ── {title} ──"
        start_y = h // 2 - len(lines) // 2 - 1
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            self.app.stdscr.addstr(start_y, w // 2 - len(title_str) // 2, title_str[:w-2])
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        except curses.error:
            pass
        for i, line in enumerate(lines):
            try:
                self.app.stdscr.attron(curses.color_pair(COLOR_MENU))
                self.app.stdscr.addstr(start_y + 1 + i, 4, line[:w-8])
                self.app.stdscr.attroff(curses.color_pair(COLOR_MENU))
            except curses.error:
                pass
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('ytui.py').read()); print('OK')"`

---

### Task 4: MainMenu — Borderless Redesign

**Files:**
- Modify: `ytui.py:389-441` (MainMenu.render + _handle_mouse_click)

- [ ] **Step 1: Rewrite MainMenu.render**

Replace lines 389-434 with:

```python
    def render(self):
        h, w = self.app.stdscr.getmaxyx()
        self.app.stdscr.clear()

        def cx(text):
            return w // 2 - len(text) // 2

        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            self.app.stdscr.addstr(4, cx("── ytui v1.0 ──"), "── ytui v1.0 ──"[:w-2])
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE))
            self.app.stdscr.addstr(5, cx("yt-dlp Terminal UI"), "yt-dlp Terminal UI"[:w-2])
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE))
        except curses.error:
            pass

        for i, (label, _) in enumerate(self.items):
            y = 7 + i
            prefix = "\u25b6" if i == self.idx else " "
            item_str = f"  {prefix} {label}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 4, item_str[:w-8])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        theme = self.app.config["theme"]
        dot = "\u25cf" if theme == "dark" else "\u25cb"
        theme_str = f"  {dot} Theme: {theme.capitalize()}"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_MENU))
            self.app.stdscr.addstr(7 + len(self.items) + 1, 4, theme_str[:w-8])
            self.app.stdscr.attroff(curses.color_pair(COLOR_MENU))
        except curses.error:
            pass

        self.draw_status("\u2191/\u2193 navigate  Enter select  q quit  t toggle theme")
```

- [ ] **Step 2: Remove _theme_btn and _handle_mouse_click**

Delete line 387 (`self._theme_btn = None`). Delete the `_handle_mouse_click` method (around lines 438-444). Remove the line that assigned `self._theme_btn` (old line 431, now part of deleted render).

- [ ] **Step 3: Syntax check**

Run: `python3 -c "import ast; ast.parse(open('ytui.py').read()); print('OK')"`

---

### Task 5: FormatSelector Overlay — Borderless

**Files:**
- Modify: `ytui.py:935-965` (_render_preset_overlay)

- [ ] **Step 1: Rewrite _render_preset_overlay**

Replace lines 935-965 with:

```python
    def _render_preset_overlay(self, h, w):
        title = "── Quality Preset ──"
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
            self.app.stdscr.addstr(4, w // 2 - len(title) // 2, title[:w-2])
            self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        except curses.error:
            pass

        for i, (name, _) in enumerate(FORMAT_PRESETS):
            y = 6 + i
            prefix = "\u25b6 " if i == self.preset_idx else "  "
            item_str = f"  {prefix}{name}"
            attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if i == self.preset_idx else curses.color_pair(COLOR_MENU)
            try:
                self.app.stdscr.attron(attr)
                self.app.stdscr.addstr(y, 8, item_str[:w-16])
                self.app.stdscr.attroff(attr)
            except curses.error:
                pass

        self.draw_status("\u2191/\u2193 navigate  Enter select  Esc back")
```

- [ ] **Step 2: Syntax check**

---

### Task 6: SubtitleSelector — Borderless Columns

**Files:**
- Modify: `ytui.py:1081-1126` (draw_column inner function)

- [ ] **Step 1: Rewrite draw_column**

Replace lines 1081-1126 with:

```python
        def draw_column(x, title, items, is_active):
            col_color = COLOR_TITLE if is_active else COLOR_MENU
            header = f"  {title} ({len(items)})"
            try:
                self.app.stdscr.attron(curses.color_pair(col_color) | curses.A_BOLD)
                self.app.stdscr.addstr(3, x, header[:col_w+2])
                self.app.stdscr.attroff(curses.color_pair(col_color) | curses.A_BOLD)
            except curses.error:
                pass

            active_items = self._active_items()
            for row in range(max_rows):
                y = 4 + row
                if row < len(items):
                    orig_idx = items[row][0]
                    code, name, is_manual, checked = items[row][1]
                    is_sel = is_active and orig_idx == self._active_item_idx()
                    cb = "\u2713" if checked else " "
                    dot = "\u25cf" if is_manual else "\u25cb"
                    line = f"  [{cb}] {name:<{col_w-14}}{code:>4} {dot}"
                    attr = curses.color_pair(COLOR_SEL) | curses.A_REVERSE if is_sel else curses.color_pair(COLOR_MENU)
                    try:
                        self.app.stdscr.attron(attr)
                        self.app.stdscr.addstr(y, x, line[:col_w+2])
                        self.app.stdscr.attroff(attr)
                    except curses.error:
                        pass

            # bottom separator (just empty spacing instead of └─┘)
```

Also update the empty row fallback and bottom border. Remove the `└─ ─┘` border at line 1121-1124.

- [ ] **Step 2: Syntax check**

---

### Task 7: Full Verification

- [ ] **Step 1: Check syntax once more**

Run: `python3 -c "import ast; ast.parse(open('ytui.py').read()); print('OK')"`

- [ ] **Step 2: Check no box-drawing chars remain in UI code**

Run: `python3 -c "
import re
bad = re.compile(r'[\u2500-\u257f]')
with open('ytui.py') as f:
    for i, line in enumerate(f, 1):
        if bad.search(line):
            print(f'Line {i}: box char found')
"`

Expected: no output (or only false positives in comments/docstrings)

- [ ] **Step 3: Launch ytui (1 second, just to verify no crash)**

Run: `timeout 1 python3 ytui.py 2>&1 || true`

Expected: no traceback. Process exits cleanly after 1s timeout.
