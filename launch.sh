#!/usr/bin/env bash
# launch.sh — starts the Office Robot voice pipeline
# Run this every time you want to start the robot (after setup.sh):
#   ./launch.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[robot]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn] ${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; }

# ── 1. Detect ROS2 distro ─────────────────────────────────────────────────────
UBUNTU_CODENAME=$(. /etc/os-release && echo "$UBUNTU_CODENAME")
case "$UBUNTU_CODENAME" in
    jammy) ROS_DISTRO="humble" ;;
    noble) ROS_DISTRO="jazzy"  ;;
    *)     ROS_DISTRO="humble" ;;
esac

ROS_SETUP="/opt/ros/${ROS_DISTRO}/setup.bash"
WS_SETUP="$REPO_DIR/backend/install/setup.bash"

# ── 2. Check the workspace has been built ─────────────────────────────────────
if [ ! -f "$WS_SETUP" ]; then
    err "Workspace not built. Run ./setup.sh first."
    exit 1
fi

# ── 3. Source both ROS2 and the workspace ─────────────────────────────────────
# ROS2 setup files reference AMENT_TRACE_SETUP_FILES without initialising it;
# lift -u (nounset) around both source calls to avoid "unbound variable" errors.
set +u
# shellcheck source=/dev/null
source "$ROS_SETUP"
# shellcheck source=/dev/null
source "$WS_SETUP"
set -u
info "ROS2 $ROS_DISTRO + workspace sourced."

# ── 4. Start ollama if it is not already running ──────────────────────────────
if pgrep -x ollama > /dev/null 2>&1; then
    info "ollama is already running."
else
    info "Starting ollama in the background..."
    ollama serve > /tmp/ollama.log 2>&1 &
    # Give it a moment to open its port before the first LLM call
    sleep 2
fi

# ── 5. Launch all ROS2 nodes ──────────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "${GREEN}  Office Robot — Starting voice pipeline${NC}"
echo "  Say 'Robot' to wake it up."
echo "  Press Ctrl+C to stop."
echo "======================================================"
echo ""

ros2 launch office_robot voice_pipeline.launch.py
