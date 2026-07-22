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

### Prerequisites

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)

### Install

```bash
# 1. Clone the repo
git clone https://github.com/bhumi0624/ytui.git
cd ytui

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run it!
python3 ytui.py
```

### Termux (Android)

```bash
pkg update && pkg install python yt-dlp git
git clone https://github.com/bhumi0624/ytui.git
cd ytui
python3 ytui.py
```

### Alias (optional)

Add to your `~/.zshrc` or `~/.bashrc`:

```bash
alias ytui='python3 ~/dev/video-downloader/ytui/ytui.py'
```

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
| `q` | Quit / Cancel download |

---

## 🗂️ Project Structure

```
ytui/
├── ytui.py              # Main application (single file)
├── requirements.txt     # Python dependencies
└── README.md            # This file
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
