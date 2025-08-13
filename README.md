

# v4l2loopback Setup for Multi-Camera Streaming

## Overview

This project utilizes a custom version of the `v4l2loopback` kernel module, hosted at [https://github.com/aab18011/v4l2loopback.git](https://github.com/aab18011/v4l2loopback.git), to create more than 8 dummy video devices on a Linux system. These dummy devices enable persistent connections to multiple IP Power over Ethernet (PoE) cameras via RTMP streams, which are then used in OBS Studio for seamless live streaming, particularly for dynamic events like paintball games.

## Purpose

When switching scenes in OBS Studio, connecting directly to IP PoE cameras can cause a brief blackout or frozen image due to the time required for network and RTMP stream handshakes. By using the `v4l2loopback` module to create dummy video devices (up to 16 in this setup), each camera's RTMP stream can be continuously attached to a dedicated `/dev/videoX` device. This ensures that OBS can switch between camera feeds instantly without reconnecting to the network stream, eliminating lag and blackouts during live broadcasts.

## How It Works

1. **Custom v4l2loopback Module**:
   - The modified `v4l2loopback` module from the GitHub repository supports creating more than the default 8 dummy video devices (configured for 16 in this setup).
   - The module is managed via DKMS (Dynamic Kernel Module Support) to ensure it is built and installed for the current kernel and updated automatically when new commits are available in the repository.

2. **Setup Script (`setup_v4l2loopback.sh`)**:
   - Located at `/usr/local/bin/setup_v4l2loopback.sh`, this script:
     - Clones or updates the `v4l2loopback` repository.
     - Checks for updates by comparing the current commit with the latest on the `main` branch.
     - Removes broken or outdated DKMS entries and old module versions.
     - Builds and installs the custom module for the current kernel using DKMS.
     - Loads the module with parameters to create 16 dummy video devices (`/dev/video0` to `/dev/video15`) with labels `Cam0` to `Cam15`.

3. **Streaming Script**:
   - A secondary script (e.g., the one adapted from your old code) performs the following:
     - Runs the `setup_v4l2loopback.sh` script to ensure the module is installed and loaded.
     - Loads additional v4l2-related kernel modules if needed (e.g., `videodev`, `tuner`).
     - Uses `ffmpeg` to attach RTMP streams from IP PoE cameras to each dummy video device (`/dev/video0` to `/dev/video15`).
     - Launches OBS Studio (via Flatpak) to utilize the dummy video devices as sources for scene switching.

4. **Persistent Streaming**:
   - Each camera's RTMP stream (e.g., `rtmp://192.168.1.XXX/bcs/channelX_main.bcs`) is attached to a specific dummy video device using `ffmpeg`.
   - The streams remain active, allowing OBS to switch between devices without re-establishing network connections, thus avoiding blackouts or freezes.

## Benefits

- **Seamless Scene Switching**: Eliminates lag and blackouts when switching between camera feeds in OBS, critical for live events like paintball games.
- **Scalability**: Supports up to 16 cameras, surpassing the default `v4l2loopback` limit of 8 devices.
- **Automation**: The DKMS setup ensures the module is always up-to-date with the latest repository changes and compatible with the current kernel.
- **Reliability**: Persistent RTMP connections prevent disruptions during live streams.

## Setup Instructions

1. **Install Dependencies**:
   - Ensure `git`, `dkms`, `ffmpeg`, and OBS Studio (via Flatpak) are installed on your Linux system.
   - Example for Ubuntu/Debian:
     ```bash
     sudo apt update
     sudo apt install git dkms ffmpeg flatpak
     flatpak install flathub com.obsproject.Studio
     ```

2. **Deploy the Setup Script**:
   - Save the `setup_v4l2loopback.sh` script to `/usr/local/bin/setup_v4l2loopback.sh` and make it executable:
     ```bash
     sudo chmod +x /usr/local/bin/setup_v4l2loopback.sh
     ```

3. **Create a Systemd Service**:
   - Create a systemd service file at `/etc/systemd/system/v4l2loopback-setup.service` to run the setup script at boot:
     ```ini
     [Unit]
     Description=Setup v4l2loopback after boot
     After=network.target

     [Service]
     Type=oneshot
     ExecStart=/usr/local/bin/setup_v4l2loopback.sh
     RemainAfterExit=yes

     [Install]
     WantedBy=multi-user.target
     ```
   - Enable the service:
     ```bash
     sudo systemctl enable v4l2loopback-setup.service
     ```

4. **Deploy the Streaming Script**:
   - Save the streaming script (e.g., `start_streaming.sh`) to a convenient location (e.g., `/usr/local/bin/start_streaming.sh`) and make it executable:
     ```bash
     sudo chmod +x /usr/local/bin/start_streaming.sh
     ```
   - Update the script with the correct RTMP URLs, IP addresses, and credentials for your cameras.

5. **Run the Streaming Script**:
   - Execute the streaming script manually or automate it (e.g., via a systemd service or cron job):
     ```bash
     /usr/local/bin/start_streaming.sh
     ```

## Usage in OBS Studio

- In OBS Studio, add each dummy video device (`/dev/video0` to `/dev/video15`) as a **Video Capture Device (V4L2)** source.
- Configure your scenes to use these sources, allowing instant switching between camera feeds without network reconnection delays.

## Notes

- **Camera Configuration**: Ensure each camera's RTMP URL is correctly specified in the streaming script (e.g., replace `192.168.1.XXX` and `YYY` with your camera's IP and password).
- **Systemd Service**: The provided `v4l2loopback-setup.service` ensures the module is loaded at boot, but you may need a separate service for the streaming script if automation is desired.
- **Troubleshooting**:
  - Check `systemctl status v4l2loopback-setup.service` for DKMS or module loading issues.
  - Verify RTMP streams with `ffmpeg` manually if a camera feed fails.
  - Ensure the kernel headers for your current kernel are installed (`sudo apt install linux-headers-$(uname -r)`).

## Repository

The custom `v4l2loopback` module is maintained at [https://github.com/aab18011/v4l2loopback.git](https://github.com/aab18011/v4l2loopback.git). Contributions or issues can be reported there.

