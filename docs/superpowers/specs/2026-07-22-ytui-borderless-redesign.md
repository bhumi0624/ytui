# YTUI Borderless & Theme Redesign

**Date:** 2026-07-22
**Status:** Draft

## Problem

- Vertical borders (`║`, `│`) in dialog boxes, menus, and column headers are misaligned with box edges, creating a visibly ragged right edge.
- Mixed box-drawing styles (heavy `╔╗╚╝║═╠╣` for dialogs/menus vs. light `┌┐└┘│─` for buttons) look inconsistent.
- Light theme uses harsh `COLOR_BLUE` and `COLOR_WHITE` on `COLOR_BLUE`, which is uncomfortable on light-terminal backgrounds.
- `draw_button()` (light borders) is dead code — never called.

## Solution

Remove all box borders from the TUI. Replace with whitespace/indentation, horizontal separators (`─`), and color-only styling. Update light theme to a modern minimal palette (bold/dim/reverse, no harsh colors).

## Scope

All changes in `/root/dev/video-downloader/ytui/ytui.py` — single-file project.

---

## Section 1: Theme — Modern Minimal (Option 1)

### Dark theme — unchanged (already acceptable)
```python
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
```

### Light theme — minimal, no harsh blue
```python
THEME_LIGHT = {
    "menu":      (curses.COLOR_BLACK, -1),
    "title":     (curses.COLOR_BLACK, -1),  + BOLD
    "sel":       (-1, -1),                  + A_REVERSE
    "status":    (curses.COLOR_WHITE, curses.COLOR_BLUE),
    "progress":  (curses.COLOR_GREEN, -1),
    "header":    (-1, -1),                  + A_DIM
    "info":      (-1, -1),                  + A_DIM
    "error":     (curses.COLOR_RED, -1),
}
```

### How theme is applied
Theme values are applied in `App._init_curses()` via `curses.init_pair()`. Each COLOR_* constant maps to a pair. The `A_BOLD`/`A_REVERSE`/`A_DIM` attributes are appended at render time in each `draw_*` call — the theme dict stores only foreground/background color pairs.

---

## Section 2: MainMenu — Borderless List

### Before
```python
put(box_y, "╔" + "═" * (box_w - 2) + "╗")
put(box_y + 1, f"║{'ytui v1.0':^{box_w-2}}║")
put(box_y + 2, f"║{'yt-dlp Terminal UI':^{box_w-2}}║")
put(box_y + 3, "╠" + "═" * (box_w - 2) + "╣")
for i, (label, _) in enumerate(self.items):
    put(y, f"║ {prefix} {label:<29} ║")
put(item_end, "╠" + "═" * (box_w - 2) + "╣")
put(btn_y, f"║   {dot} Theme: {theme.capitalize():<22} ║")
put(btn_y + 1, "╚" + "═" * (box_w - 2) + "╝")
```

### After
```
          ── ytui v1.0 ──                    (center, COLOR_TITLE|BOLD)
         yt-dlp Terminal UI                  (center, COLOR_TITLE)

    ▶ Search YouTube                         (indent 4, "▶" if selected)
      Download URL
      ...
      Exit

    ○ Theme: Dark                            (indent 4, "●"/"○")
───────────────────────────────────────       (draw_status separator)
```

- No `╔╗╚╝║═╠╣` characters.
- No `box_x` / `box_y` / `box_w` calculations.
- Title: centered via string padding.
- Items: 4-space indent, selected item gets `▶ prefix` + `COLOR_SEL|A_REVERSE`.
- Theme: inline at bottom, `●` = dark, `○` = light.
- Status bar separator `─` * w remains unchanged in `draw_status()`.

### Code structure
- `MainMenu.render` is entirely rewritten.
- `MainMenu._theme_btn` removed (no more box-based hit-testing; simplify to key-only toggle).
- Mouse handler `_handle_mouse_click` simplified or removed.

---

## Section 3: draw_dialog — No-Box Message

### Before
```python
put(box_y, "╔" + "═" * (box_w - 2) + "╗")
put(box_y + 1, f"║ {title:^{box_w-4}} ║")
put(box_y + 2, "╠" + "═" * (box_w - 2) + "╣")
for i, line in enumerate(lines):
    put(box_y + 3 + i, f"║ {line:<{box_w-4}} ║")
put(box_y + 3 + len(lines), "╚" + "═" * (box_w - 2) + "╝")
```

### After
```python
def draw_dialog(self, title, message):
    h, w = self.app.stdscr.getmaxyx()
    lines = message.split("\n")
    start_y = h // 2 - len(lines) // 2

    # Title in bold+color, centered
    title_str = f"  ── {title} ──"
    try:
        self.app.stdscr.attron(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        self.app.stdscr.addstr(start_y - 1, w // 2 - len(title_str) // 2, title_str)
        self.app.stdscr.attroff(curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
    except curses.error:
        pass

    # Message lines in menu color, centered
    for i, line in enumerate(lines):
        try:
            self.app.stdscr.attron(curses.color_pair(COLOR_MENU))
            self.app.stdscr.addstr(start_y + i, w // 2 - len(line) // 2, line[:w-2])
            self.app.stdscr.attroff(curses.color_pair(COLOR_MENU))
        except curses.error:
            pass
```

- No `box_w` parameter needed.
- `width` parameter removed from signature.
- All callers updated (7 callsites, each passing `"Error"` or similar title + message string).

---

## Section 4: FormatSelector Preset Overlay — Borderless

### Before
```python
put(box_y, "╔" + "═" * (box_w - 2) + "╗")
put(box_y + 1, f"║ {'Quality Preset':^{box_w-6}} ║")
put(box_y + 2, "╠" + "═" * (box_w - 2) + "╣")
for i, (name, fmt_str) in enumerate(FORMAT_PRESETS):
    y, prefix, attr = ...
    self.app.stdscr.addstr(y, box_x, f"║ {prefix}{name:<{box_w-7}} ║")
put(bottom_y, "╚" + "═" * (box_w - 2) + "╝")
```

### After
```
            ── Quality Preset ──           (center, COLOR_TITLE|BOLD)

         ▶ 360p                            (indent 8, ▶ / space)
           480p
           720p
           1080p
           4K
           Audio Only
```

No box characters. Same center-alignment approach as MainMenu. Indent at 8 spaces.

---

## Section 5: SubtitleSelector Columns — No Border Columns

### Before
```python
header = f"┌─ {title} ({len(items)}) " + "─" * col_w + "┐"
# rows:
line = f"│ {cb} {name:<col_w-16}{code:>4} {dot} │"
# bottom:
f"└{'─' * col_w}┘"
```

### After
```
   Manual (5)                          Auto (3)
   ──────────────────────────           ─────────────────────────
   [✓] English           en ●          [ ] Indonesian     id ○
   [✓] Japanese          ko ●          [ ] Korean         ko ○
```

- Remove `┌─ ─┐` header borders → use bold title string.
- Remove `│` from rows → use pure text with space padding.
- Remove `└─ ─┘` bottom border → use `─` separator line above first items.
- Column width `col_w` computed the same, but without the 2-char border overhead.

### Code structure
- `draw_column()` inner function rewritten.
- `col_w` recomputed: `col_w = (w // 2) - 5` becomes `(w // 2) - 3` (no border).

---

## Section 6: draw_button — Remove Dead Code

`draw_button()` at line 261 is defined but never called anywhere. Remove it entirely.

---

## Files Changed

| File | Lines | Change |
|---|---|---|
| `ytui.py` | 41-61 | Theme definitions (light) |
| `ytui.py` | 261-288 | Remove `draw_button()` |
| `ytui.py` | 347-372 | Rewrite `draw_dialog()` |
| `ytui.py` | 389-441 | Rewrite `MainMenu.render()` |
| `ytui.py` | 935-965 | Rewrite `_render_preset_overlay()` |
| `ytui.py` | 1078-1126 | Rewrite `SubtitleSelector.draw_column()` |
| `ytui.py` | ~7 callers | Update `draw_dialog()` calls (remove `width` arg) |

## Testing

- Run `python3 ytui.py` on terminal.
- Navigate all screens: MainMenu → Search/URL → Format select → Subtitle → Folder → Download.
- Verify no box-drawing characters appear.
- Verify all text is readable in both dark and light themes.
- Verify `Ctrl+T` toggles theme correctly.
- Test at narrow terminal widths (80x24) to ensure no crashes.
