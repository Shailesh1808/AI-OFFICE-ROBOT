#!/usr/bin/env bash
# setup.sh — one-shot setup from a fresh clone
# Run once on the Jetson or any Ubuntu machine:
#   chmod +x setup.sh && ./setup.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "\n${GREEN}[setup]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn] ${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; }

echo ""
echo "=============================================="
echo "  Office Robot — One-Shot Setup"
echo "=============================================="

# ── 1. Detect Ubuntu version → ROS2 distro ────────────────────────────────────
UBUNTU_CODENAME=$(. /etc/os-release && echo "$UBUNTU_CODENAME")
case "$UBUNTU_CODENAME" in
    jammy) ROS_DISTRO="humble" ;;
    noble) ROS_DISTRO="jazzy"  ;;
    *)
        warn "Unrecognised Ubuntu codename '$UBUNTU_CODENAME'. Defaulting to humble."
        ROS_DISTRO="humble"
        ;;
esac
info "Ubuntu: $UBUNTU_CODENAME  →  ROS2: $ROS_DISTRO"

# ── 2. Fix ROS2 apt source conflicts ──────────────────────────────────────────
info "Checking apt sources..."
if sudo apt-get update 2>&1 | grep -q "Conflicting values"; then
    warn "ROS2 source conflict detected — fixing..."
    sudo rm -f /etc/apt/sources.list.d/ros2-latest.list \
               /etc/apt/sources.list.d/ros2.list
    sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu ${UBUNTU_CODENAME} main" \
        | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
fi
sudo apt-get update -qq

# ── 3. System/Python/ollama dependencies ──────────────────────────────────────
info "Running install.sh..."
chmod +x install.sh
./install.sh

# ── 4. Piper TTS ──────────────────────────────────────────────────────────────
info "Running install_piper.sh..."
chmod +x install_piper.sh
./install_piper.sh

# ── 5. Source ROS2 ────────────────────────────────────────────────────────────
ROS_SETUP="/opt/ros/${ROS_DISTRO}/setup.bash"
if [ ! -f "$ROS_SETUP" ]; then
    err "ROS2 setup not found at $ROS_SETUP"
    err "Install ROS2 $ROS_DISTRO first, then re-run setup.sh"
    exit 1
fi
# shellcheck source=/dev/null
source "$ROS_SETUP"
info "ROS2 $ROS_DISTRO sourced."

# ── 6. Build ROS2 package ─────────────────────────────────────────────────────
info "Building office_robot package..."
cd "$REPO_DIR/backend"
colcon build --packages-select office_robot

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo -e "${GREEN}  Setup complete!${NC}"
echo ""
echo "  To start the robot:"
echo "    ./launch.sh"
echo "=============================================="
