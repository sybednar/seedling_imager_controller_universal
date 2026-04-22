#!/usr/bin/env bash
set -euo pipefail

# Log stdout/stderr to diagnose autostart behavior
exec >> /home/sybednar/Seedling_Imager/seedling_imager_controller/autostart.log 2>&1
echo "=== $(date) Seedling Imager autostart begin ==="

# Show environment (for troubleshooting)
env | sort
echo "---"

# Let the session settle
sleep 3

# Ensure XDG runtime dir exists in graphical-session context
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

# Choose Qt platform (Wayland is typical on Pi 5; use xcb if Wayland proves fussy)
export QT_QPA_PLATFORM=wayland
# export QT_QPA_PLATFORM=xcb

# Activate venv
source /home/sybednar/Seedling_Imager/bin/activate

# Run the app
cd /home/sybednar/Seedling_Imager/seedling_imager_controller
python3 main.py

echo "=== $(date) Seedling Imager autostart end ==="
