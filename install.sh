#!/usr/bin/env bash
# install.sh — Office Robot setup script
# Target: Jetson Orin Nano, JetPack 6.1 (Ubuntu 22.04 aarch64)
#
# Run once on the Jetson before building:
#   chmod +x install.sh && ./install.sh

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}→${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }

echo "=================================================="
echo "  Office Robot — Install (JetPack 6.1 / aarch64)"
echo "=================================================="

# ── 1. System packages ─────────────────────────────────────────────────────────
info "System packages..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-dev python3-pip build-essential \
    portaudio19-dev python3-pyaudio \
    espeak-ng libasound2-dev libsndfile1-dev \
    curl git

# ── 2. Python packages ─────────────────────────────────────────────────────────
info "Python packages..."
# --break-system-packages is needed on Ubuntu 24.04+ (PEP 668).
# On Ubuntu 22.04 it is silently ignored, so this works on both.
pip3 install --break-system-packages --upgrade pip --quiet
pip3 install --break-system-packages pyaudio webrtcvad faster-whisper requests numpy

echo ""
echo "  ┌─ GPU ASR (optional) ────────────────────────────────────────────────┐"
echo "  │  PyPI ctranslate2 aarch64 = CPU-only. For CUDA ASR on JetPack 6.1:│"
echo "  │    sudo apt install cmake libopenblas-dev                           │"
echo "  │    pip3 install 'ctranslate2>=4.4.0,<4.5.0' --no-binary :all:      │"
echo "  │  (4.4.x works with CUDA 12.2 + cuDNN 8; 4.5+ needs cuDNN 9)       │"
echo "  └─────────────────────────────────────────────────────────────────────┘"
echo ""

# ── 3. ollama ──────────────────────────────────────────────────────────────────
info "ollama..."
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    info "ollama already installed."
fi

info "Starting ollama (background)..."
if ! pgrep -x ollama > /dev/null 2>&1; then
    nohup ollama serve > /tmp/ollama.log 2>&1 & sleep 4
fi

info "Pulling llama3.2:3b (~2 GB)..."
ollama pull llama3.2:3b

# ── 4. Pre-download Whisper model ─────────────────────────────────────────────
info "Pre-downloading Whisper base.en..."
python3 - <<'PYEOF'
from faster_whisper import WhisperModel, download_model
try:
    download_model('base.en')
    print("  base.en ready.")
except Exception as e:
    print(f"  Will download on first run: {e}")
PYEOF

# ── 5. Verify espeak-ng ───────────────────────────────────────────────────────
info "espeak-ng: $(espeak-ng --version 2>&1 | head -1)"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo -e "${GREEN}  Install complete!${NC}"
echo ""
echo "  Build and run:"
echo ""
echo "    cd <repo>/backend"
echo "    colcon build --packages-select office_robot"
echo "    source install/setup.bash"
echo ""
echo "    # In a separate terminal — keep running:"
echo "    ollama serve"
echo ""
echo "    ros2 launch office_robot voice_pipeline.launch.py"
echo ""
echo "  Diagnostics:"
echo "    python3 find_audio_device.py   # find mic device name hint"
echo "    aplay -l                       # find USB speaker card name"
echo "=================================================="
