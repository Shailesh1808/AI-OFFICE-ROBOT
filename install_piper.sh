#!/usr/bin/env bash
# install_piper.sh — installs Piper TTS binary + English voice model
# Supports: x86_64 (laptop/desktop) and aarch64 (Jetson Orin Nano)
# Run this once, then rebuild and relaunch the pipeline.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }

PIPER_DIR="/usr/local/lib/piper"
VOICE_DIR="/usr/local/share/piper-voices"
VOICE="en_US-lessac-medium"
HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium"

echo "========================================"
echo "  Piper TTS Install"
echo "========================================"

# ── Detect architecture ────────────────────────────────────────────────────────
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  PIPER_TAR="piper_linux_x86_64.tar.gz" ;;
    aarch64) PIPER_TAR="piper_linux_aarch64.tar.gz" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

PIPER_URL="https://github.com/rhasspy/piper/releases/latest/download/${PIPER_TAR}"

# ── Download Piper binary ──────────────────────────────────────────────────────
info "Downloading Piper binary for ${ARCH}..."
wget -q --show-progress -O /tmp/piper.tar.gz "$PIPER_URL"

info "Installing to ${PIPER_DIR}..."
sudo mkdir -p "$PIPER_DIR"
sudo tar -xzf /tmp/piper.tar.gz -C /usr/local/lib/
rm /tmp/piper.tar.gz

# Ensure aplay is available for audio playback
sudo apt-get install -y alsa-utils -qq

# ── Download voice model ───────────────────────────────────────────────────────
info "Downloading voice: ${VOICE} (~60 MB)..."
sudo mkdir -p "$VOICE_DIR"
sudo wget -q --show-progress -O "${VOICE_DIR}/${VOICE}.onnx"      "${HF_BASE}/${VOICE}.onnx"
sudo wget -q --show-progress -O "${VOICE_DIR}/${VOICE}.onnx.json" "${HF_BASE}/${VOICE}.onnx.json"

# ── Test ───────────────────────────────────────────────────────────────────────
echo ""
info "Testing Piper..."
echo "Hello, I am your office robot." \
    | "${PIPER_DIR}/piper" --model "${VOICE_DIR}/${VOICE}.onnx" --output-raw --quiet \
    | aplay -q -r 22050 -f S16_LE -c 1 && echo "  Audio test passed." \
    || warn "Audio test failed — check your speaker setup."

echo ""
echo "========================================"
echo -e "${GREEN}  Piper installed!${NC}"
echo ""
echo "  Now rebuild and relaunch:"
echo "    cd ~/AI-OFFICE-ROBOT/backend"
echo "    colcon build --packages-select office_robot"
echo "    source install/setup.bash"
echo "    ros2 launch office_robot voice_pipeline.launch.py"
echo "========================================"
