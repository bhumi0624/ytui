# YTUI Easy Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable single-command YTUI install via `curl ... | bash` (Linux/Termux/macOS) and `pipx install ytui` (Windows).

**Architecture:** Add `pyproject.toml` for pip/pipx support, create `install.sh` for curl-to-bash installer, minor modification to `ytui.py` for dependency check at startup, update README.

**Tech Stack:** Bash, Python, setuptools, curl, shell config management

## Global Constraints

- No new runtime dependencies — yt-dlp is checked via `shutil.which` at runtime, not hard-dep
- `install.sh` must work on Linux, macOS, AND Termux (Android) without `sudo`
- All operations idempotent — re-running installer is safe
- Shell config modification must backup original file first
- Python >= 3.8 required
- `~/.local/bin/` used for wrapper script (XDG standard)

---

### Task 1: Python packaging & dependency check

**Files:**
- Create: `pyproject.toml`
- Modify: `ytui.py` (line 2499–2503)

**Interfaces:**
- Consumes: existing `main()` at bottom of `ytui.py`
- Produces: `ytui:main` entry point consumable by pip/pipx; `check_dependencies()` guard in main()

- [ ] **Step 1: Create `pyproject.toml`**

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

- [ ] **Step 2: Modify `ytui.py` — add dependency check at top of `main()`**

Replace lines 2499–2503 from:

```python
def main():
    try:
        curses.wrapper(lambda stdscr: App(stdscr).run())
    except KeyboardInterrupt:
        pass
```

to:

```python
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
```

- [ ] **Step 3: Test locally**

```bash
cd /root/dev/video-downloader/ytui
pip install -e .
which ytui
```

Expected: `ytui` resolves to an entry point (shows path in `~/.local/bin/` or similar).

```bash
# Quick test — should show error because yt-dlp might not be in PATH in test env
ytui 2>&1 | head -5
```

- [ ] **Step 4: Commit**

```bash
cd /root/dev/video-downloader/ytui
git add pyproject.toml ytui.py
git commit -m "feat: add pyproject.toml and dependency check"
```

---

### Task 2: `install.sh` — curl-to-bash installer

**Files:**
- Create: `install.sh`

**Interfaces:**
- Produces: a standalone bash script that can be curl-piped
- Consumes: nothing (self-contained)

- [ ] **Step 1: Write the installer script**

`install.sh` — full installer:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="bhumi0624/ytui"
RAW_URL="https://raw.githubusercontent.com/$REPO/main/ytui.py"
INSTALL_DIR="$HOME/.local/share/ytui"
BIN_DIR="$HOME/.local/bin"
WRAPPER="$BIN_DIR/ytui"

# ─── Colors ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'

info()  { printf "${CYAN}%s${NC}\n" "$*"; }
ok()    { printf "${GREEN}%s${NC}\n" "$*"; }
err()   { printf "${RED}%s${NC}\n" "$*" >&2; }

# ─── Help / Uninstall ────────────────────────────────────
usage() {
    cat <<EOF
Usage: curl -sSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash
       curl -sSL https://raw.githubusercontent.com/$REPO/main/install.sh | bash -s -- --uninstall

Options:
  --help        Show this help
  --uninstall   Remove YTUI and all installed files
EOF
    exit 0
}

uninstall() {
    info "Uninstalling YTUI..."
    rm -f "$WRAPPER"
    rm -rf "$INSTALL_DIR"
    # Remove PATH lines from shell configs (simple version — exact match)
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.config/fish/config.fish"; do
        [ -f "$rc" ] && sed -i '/.local\/bin\/ytui/d' "$rc" 2>/dev/null || true
    done
    ok "YTUI has been removed."
    exit 0
}

[ "${1:-}" = "--help" ] && usage
[ "${1:-}" = "--uninstall" ] && uninstall

# ─── OS Detection ────────────────────────────────────────
detect_os() {
    if [ -n "${TERMUX_VERSION:-}" ]; then
        echo "termux"
    elif [ "$(uname -s)" = "Darwin" ]; then
        echo "macos"
    elif [ "$(uname -s)" = "Linux" ]; then
        echo "linux"
    else
        err "Unsupported OS: $(uname -s)"
        err "Try installing via pipx instead: pipx install ytui"
        exit 1
    fi
}

# ─── Package Manager Helpers ─────────────────────────────
install_pkg() {
    local os=$1 pkg=$2
    case "$os" in
        termux) pkg install -y "$pkg" ;;
        linux)
            if command -v apt &>/dev/null; then
                sudo apt update && sudo apt install -y "$pkg"
            elif command -v dnf &>/dev/null; then
                sudo dnf install -y "$pkg"
            elif command -v yum &>/dev/null; then
                sudo yum install -y "$pkg"
            else
                err "No known package manager. Install $pkg manually."
                return 1
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install "$pkg"
            else
                err "Homebrew not found. Install $pkg manually."
                return 1
            fi
            ;;
    esac
}

# ─── Main Install ────────────────────────────────────────
OS=$(detect_os)
info "Detected OS: $OS"

# Step 1: Check Python 3.8+
info "Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0")
        if [ "$(echo "$ver" | cut -d. -f1)" -ge 3 ] && [ "$(echo "$ver" | cut -d. -f2)" -ge 8 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    info "Installing Python 3..."
    install_pkg "$OS" "python3"
    PYTHON="python3"
fi
ok "Python: $($PYTHON --version)"

# Step 2: Install yt-dlp
info "Installing yt-dlp..."
if command -v yt-dlp &>/dev/null; then
    ok "yt-dlp already installed: $(yt-dlp --version 2>/dev/null || echo 'ok')"
else
    if [ "$OS" = "termux" ]; then
        install_pkg "$OS" "yt-dlp"
    else
        $PYTHON -m pip install --upgrade yt-dlp
    fi
    ok "yt-dlp installed: $(yt-dlp --version 2>/dev/null || echo 'ok')"
fi

# Step 3: Download ytui.py
info "Downloading YTUI..."
mkdir -p "$INSTALL_DIR"
if command -v curl &>/dev/null; then
    curl -sSL "$RAW_URL" -o "$INSTALL_DIR/ytui.py"
elif command -v wget &>/dev/null; then
    wget -q "$RAW_URL" -O "$INSTALL_DIR/ytui.py"
else
    err "Neither curl nor wget found. Install one and retry."
    exit 1
fi
ok "Downloaded to $INSTALL_DIR/ytui.py"

# Step 4: Create wrapper
info "Creating wrapper script..."
mkdir -p "$BIN_DIR"
cat > "$WRAPPER" <<WRAPPER
#!/usr/bin/env sh
exec $PYTHON "$INSTALL_DIR/ytui.py" "\$@"
WRAPPER
chmod +x "$WRAPPER"
ok "Wrapper created at $WRAPPER"

# Step 5: Ensure ~/.local/bin is in PATH
info "Setting up PATH..."
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
FISH_LINE='set -gx PATH $HOME/.local/bin $PATH'
ADDED=false

add_to_rc() {
    local file=$1 line=$2
    [ ! -f "$file" ] && touch "$file"
    if ! grep -qxF "$line" "$file"; then
        cp "$file" "$file.bak" 2>/dev/null || true
        printf "\n# Added by YTUI installer\n%s\n" "$line" >> "$file"
        ADDED=true
    fi
}

add_to_rc "$HOME/.bashrc" "$PATH_LINE"
add_to_rc "$HOME/.zshrc" "$PATH_LINE"
mkdir -p "$HOME/.config/fish"
add_to_rc "$HOME/.config/fish/config.fish" "$FISH_LINE"

if [ "$ADDED" = true ]; then
    ok "Shell config updated. Restart your terminal or run: source ~/.bashrc"
fi

# ─── Done ────────────────────────────────────────────────
echo ""
printf "${GREEN}${BOLD}✓ YTUI installed successfully!${NC}\n"
printf "${GREEN}Type ${BOLD}ytui${NC}${GREEN} in your terminal to run it.${NC}\n"
echo ""
printf "${CYAN}If 'ytui' is not found, restart your terminal or run:%s${NC}\n" ""
printf "  source ~/.bashrc\n"
```

- [ ] **Step 2: Test install.sh in a safe location**

```bash
cd /root/dev/video-downloader/ytui
chmod +x install.sh
# Dry-run test: check that it prints help correctly
bash install.sh --help
```

- [ ] **Step 3: Run installer locally to verify**

```bash
cd /root/dev/video-downloader/ytui
# Simulate full install in a temp HOME
TMPDIR=$(mktemp -d)
HOME="$TMPDIR" bash install.sh
# Check what was created
ls -la "$TMPDIR/.local/bin/ytui"
ls -la "$TMPDIR/.local/share/ytui/ytui.py"
# Should exist and be executable
"$TMPDIR/.local/bin/ytui" --help 2>&1 || true
rm -rf "$TMPDIR"
```

- [ ] **Step 4: Commit**

```bash
cd /root/dev/video-downloader/ytui
git add install.sh
git commit -m "feat: add install.sh — curl-to-bash installer"
```

---

### Task 3: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update installation section in README**

Replace lines 24–61 (the old Installation section) with:

```markdown
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
```

- [ ] **Step 2: Update Project Structure section**

Replace lines 91–98 with:

```
ytui/
├── install.sh            # One-liner installer
├── pyproject.toml        # Python packaging
├── ytui.py               # Main application (single file)
├── requirements.txt      # Python dependencies
└── README.md             # This file
```

- [ ] **Step 3: Commit**

```bash
cd /root/dev/video-downloader/ytui
git add README.md
git commit -m "docs: update README with new install methods"
```

---

## Files Summary

| File | Action |
|------|--------|
| `pyproject.toml` | CREATE |
| `install.sh` | CREATE |
| `ytui.py` | MODIFY (lines 2499-2507) |
| `README.md` | MODIFY (install section + project structure) |
