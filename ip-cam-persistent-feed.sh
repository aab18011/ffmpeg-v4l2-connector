#!/bin/bash
set -euo pipefail

# If needed, run the DKMS setup script to ensure the module is installed and up-to-date
#/usr/local/bin/setup_v4l2loopback.sh

# Load additional v4l2 modules if needed (these may be dependencies, but modprobe v4l2loopback should handle most)
#sudo modprobe tuner || true
#sudo modprobe v4l2-async || true
#sudo modprobe v4l2-dv-timings || true
#sudo modprobe v4l2-fwnode || true
#sudo modprobe videobuf-core || true
#sudo modprobe videobuf-dma-sg || true
#sudo modprobe videobuf-vmalloc || true
#sudo modprobe videodev || true

# Assuming the module is now loaded with devices=16 via the setup script

# Attach rtmp streams to the dummy video devices created by v4l2loopback
# Loop for 16 cameras; adjust IPs, channels, users, passwords as needed
for i in {0..15}; do
    # Example: Replace XXX with actual IP part, YYY with password
    # For each camera, assume sequential channels or adjust accordingly
    gnome-terminal -- bash -c "ffmpeg -i 'rtmp://192.168.1.XXX/bcs/channel${i}_main.bcs?channel=${i}&stream=0&user=admin&password=YYY' -f v4l2 /dev/video${i}"
done

# Now start OBS
gnome-terminal -- bash -c "flatpak run com.obsproject.Studio"
