# ytui 🎬

**yt-dlp Terminal User Interface** — Download YouTube videos & playlists from your terminal with a clean curses TUI.

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Curses](https://img.shields.io/badge/UI-curses-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## ✨ Features

- 🎯 **Single video & playlist** — auto-detect, overview, multi-select, range
- 🎵 **MP3 mode** — download as audio with one key (`m`)
- 📁 **Folder browser** — navigate, pick, or create new folders
- 📊 **Live progress** — real-time progress bar, speed, ETA
- 🔄 **Auto-merge** — video-only formats automatically merged with best audio
- 📋 **Download history** — track what you've downloaded
- ⚙️ **Settings** — configurable format, directory, history size
- 🪶 **Lightweight** — single `.py` file, no heavy frameworks

---

## 📦 Installation

### One-liner (Linux / macOS / Termux)

```bash
curl -sSL https://raw.githubusercontent.com/bhumi0624/ytui/main/install.sh | bash
```

This installs yt-dlp, downloads YTUI, and sets up the `ytui` command automatically.

### Windows

```bash
pipx install ytui
```

Or install manually:

```bash
pip install ytui
python -m ytui
```

### Prerequisites

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (installed automatically by the one-liner)

---

## 🎮 Usage

```
Main Menu
├── Download URL        → Paste link, select format, pick folder
├── Batch Download      → Download from a .txt list of URLs
├── Download History    → Browse & re-download previous downloads
├── Settings            → Default format, directory, max history
└── Exit
```

### Controls

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate |
| `Enter` | Confirm / Enter |
| `Esc` | Go back |
| `d` | Download (at format/folder/playlist screens) |
| `m` | Toggle MP3 mode |
| `Space` | Toggle select (playlist selector) |
| `a` / `n` | Select all / none (playlist selector) |
| `n` | Create new folder (folder browser) |
| `Ctrl+V` | Paste URL from clipboard (recommended over long-press paste) |
| `Ctrl+U` | Clear input field |
| `q` | Quit / Cancel download |
| `?` | Show help (at main menu) |

> **Note:** Use `Ctrl+V` to paste URLs instead of long-press paste. Long-press paste can drop special characters like `?` in some terminal emulators. `Ctrl+V` reads the clipboard directly via Android API (requires `termux-api` on Termux).

---

## 🗂️ Project Structure

```
ytui/
├── install.sh            # One-liner installer
├── pyproject.toml        # Python packaging
├── ytui.py               # Main application (single file)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

Runtime config is stored at `~/.config/ytui/`:
```
~/.config/ytui/
├── config.json          # Default format, last directory, etc.
└── history.json         # Download history
```

---

## 🔧 Technical

- **Single-file Python** app using built-in `curses` library
- **No web framework** — pure terminal UI
- **yt-dlp** invoked as subprocess with custom progress templates
- Works on Termux (Android), Linux, macOS, WSL

---

## 📝 License

MIT — use it, modify it, share it.

---

> Built with ❤️ for Termux 📱
