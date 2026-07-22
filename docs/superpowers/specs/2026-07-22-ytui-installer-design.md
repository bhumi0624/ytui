# YTUI — Easy Install System Design

## Goal

Buat YTUI bisa diinstall oleh orang awam dengan 1 command, langsung bisa dipakai tanpa setup manual alias/symlink.

## Target Platform

| Platform | Method |
|----------|--------|
| Linux (apt/yum/dnf) | `curl ... \| bash` |
| macOS | `curl ... \| bash` |
| Termux (Android) | `curl ... \| bash` |
| Windows | `pipx install ytui` (fase 1), PowerShell installer (fase 2) |

## Files Changed

| File | Change |
|------|--------|
| `install.sh` | NEW — curl-to-bash installer |
| `pyproject.toml` | NEW — Python packaging (pip/pipx support) |
| `ytui.py` | Minor: add `check_dependencies()` in `main()` |
| `README.md` | Update: add new install instructions |

## install.sh Design

### Flow

```
1. Parse args (--help, --uninstall, --version)
2. Detect OS
   - $TERMUX_VERSION → Termux
   - uname -s         → Linux (apt/yum/dnf), Darwin (brew/pip)
   - else             → error: unsupported
3. Check Python 3.8+
   - Missing → install via package manager
4. Install yt-dlp via pip
5. Create ~/.local/share/ytui/
6. Download ytui.py from GitHub raw/main
7. Write wrapper ~/.local/bin/ytui
8. chmod +x ~/.local/bin/ytui
9. Inject PATH into shell configs:
   - .bashrc  → 'export PATH="$HOME/.local/bin:$PATH"' (if missing)
   - .zshrc   → same (if missing)
   - .config/fish/config.fish → 'set -gx PATH $HOME/.local/bin $PATH' (if missing)
10. Print success message
```

### Safety

- `set -euo pipefail`
- All commands idempotent — running twice is safe
- No `sudo` — install ke `~/.local/` userland
- Backup shell config before modifying (create `.bashrc.bak` etc)

## pyproject.toml Design

Minimal Python package config:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "ytui"
version = "1.0.0"
description = "yt-dlp Terminal User Interface"
requires-python = ">=3.8"
dependencies = []

[project.scripts]
ytui = "ytui:main"
```

- yt-dlp not in `dependencies` — it's a binary, checked at runtime
- Entry point `ytui:main` enables `pipx install ytui`

## ytui.py Changes

### 1. Add check_dependencies() at top of main()

```python
def main():
    import shutil, sys
    if not shutil.which("yt-dlp"):
        print("ERROR: yt-dlp not found. Install it:")
        print("  pip install yt-dlp")
        sys.exit(1)
    try:
        curses.wrapper(lambda stdscr: App(stdscr).run())
    except KeyboardInterrupt:
        pass
```

No other changes needed — `main()` already exists and is properly gated with `if __name__`.

## README Updates

Replace installation section with simplified version:

- Linux/macOS/Termux: `curl ... | bash`
- Windows: `pipx install ytui`
- Keep prerequisite info: Python 3.8+, yt-dlp
- Remove manual git clone instructions (keep for dev)

## Update Mechanism

- Simple re-run: `curl ... | bash` again
- Overwrites ytui.py and wrapper script
- Shell configs not re-modified (idempotent check)
- Future: `ytui self-update` command

## Uninstall (future)

```bash
curl -sSL https://.../install.sh | bash -s -- --uninstall
```

Removes:
- `~/.local/share/ytui/`
- `~/.local/bin/ytui`
- Shell config lines (optional prompt)
