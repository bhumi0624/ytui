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
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.config/fish/config.fish"; do
        if [ -f "$rc" ]; then
            cp "$rc" "$rc.bak" 2>/dev/null || true
            sed -i '/^# Added by YTUI installer/d' "$rc"
            sed -i '/^export PATH="\$HOME\/.local\/bin:\$PATH"/d' "$rc"
            sed -i '/^set -gx PATH \$HOME\/.local\/bin \$PATH/d' "$rc"
        fi
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
