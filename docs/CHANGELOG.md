# Changelog

## v1.0.1 (2026-07-28)

### Bug Fixes

- **`?` character lost during URL paste** — Global `?` → HelpScreen handler in `App.run()` was intercepting `?` characters before they reached the active screen. During paste, `?` would open HelpScreen and the next character would be consumed by HelpScreen's pop handler. Moved `?` handler to `MainMenu.handle_key()` only.
- **YouTube Music Mix playlist timeout** — Auto-generated Mix playlists have many pages. yt-dlp needs to fetch all pages to determine total video count. Increased timeout from 30s to 60s in `PlaylistDetect._check()` and `FormatSelector._fetch()`.
- **YouTube Music URL support** — Added `normalize_url()` to auto-convert `music.youtube.com` to `www.youtube.com` to avoid HTTP 403 errors from yt-dlp.

### Features

- **Ctrl+V paste guidance** — URLInput now shows explicit Ctrl+V paste hint in status bar and instruction text.
- **Debug logging** — URL flow is logged to `/tmp/ytui_debug.log` for troubleshooting.

### Technical

- `normalize_url()` applied at 9 points: URLInput, PlaylistDetect (x2), FormatSelector, DownloadProgress, BatchDownload, BatchProgress, PlaylistProgress, clipboard detection.
- Cleaned stale `__pycache__/` bytecode caches.

## v1.0.0 (2026-07-22)

Initial release with full feature set:

- Main Menu with 6 options: Search, Download URL, Batch Download, History, Settings, Exit
- YouTube search via `ytsearch:` with results display
- URL input with playlist auto-detection
- Playlist Overview with Download All / Select Videos / Range options
- Multi-select playlist video picker with checkboxes
- Format Selector with all available formats + 6 quality presets
- Subtitle language picker (manual & auto-generated)
- Folder browser with create-new-folder
- Live download progress bar (gradient), speed, ETA, fragment tracking
- Sequential playlist download with per-video progress
- Batch download from `.txt` file
- Download history with re-download
- Settings: default format, directory, history limit, theme
- Dark/Light theme toggle (keyboard + mouse)
- Single-file Python curses app
