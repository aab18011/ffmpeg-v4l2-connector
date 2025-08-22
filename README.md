# Camera Streaming System Report: FFmpeg and V4L2 Loopback Integration

This report provides a comprehensive and detailed documentation of the development, setup, configuration, troubleshooting, and replication process for a camera streaming system that integrates FFmpeg with V4L2 loopback devices to stream RTMP feeds from IP cameras to virtual video devices for use in applications such as OBS Studio. The system is implemented in Python, adhering to Python's PEP 8 style guidelines, semantic versioning, and the Keep a Changelog format for version history. The focus is strictly on the FFmpeg and V4L2 loopback integration, with minimal mention of the modified V4L2 loopback module setup, as per the requirements. References to external repositories (e.g., `aab18011/v4l2loopback`) are included where relevant.

This document is formatted in Markdown for compatibility with GitHub repositories, ensuring it can be easily copied and hosted for future reference. The report assumes a Linux environment (e.g., Ubuntu) and is intended to serve as an academic, formal guide for replicating the process in case of data loss or system rebuild.

---

## Table of Contents

1. [Introduction](#introduction)
2. [System Overview](#system-overview)
3. [Version History (Keep a Changelog)](#version-history-keep-a-changelog)
4. [Code Explanation](#code-explanation)
   - [Dependencies and Configuration](#dependencies-and-configuration)
   - [Class Structure and Logic](#class-structure-and-logic)
   - [FFmpeg Command Optimization](#ffmpeg-command-optimization)
   - [Error Handling and Logging](#error-handling-and-logging)
5. [Setup Process](#setup-process)
   - [Prerequisites](#prerequisites)
   - [Configuration File](#configuration-file)
   - [Installation and Deployment](#installation-and-deployment)
6. [Troubleshooting](#troubleshooting)
   - [Common Issues and Resolutions](#common-issues-and-resolutions)
   - [Log Analysis](#log-analysis)
7. [Replication Instructions](#replication-instructions)
   - [Step-by-Step Setup](#step-by-step-setup)
   - [Verification and Testing](#verification-and-testing)
8. [Conclusion](#conclusion)
9. [References](#references)

---

## Introduction

The camera streaming system is designed to stream video feeds from multiple IP cameras over RTMP (Real-Time Messaging Protocol) to virtual V4L2 loopback devices on a Linux system, enabling seamless integration with video processing software such as OBS Studio. The system leverages FFmpeg for stream handling and V4L2 loopback devices as virtual video sinks. The primary script, `camera_streamer.py`, is a Python application that manages camera discovery, stream testing, FFmpeg process execution, and error recovery in a headless environment.

This report focuses exclusively on the FFmpeg and V4L2 loopback integration, omitting detailed setup of the modified V4L2 loopback module, which is referenced as a prerequisite (available at [aab18011/v4l2loopback](https://github.com/aab18011/v4l2loopback)). The system is designed to be robust, fault-tolerant, and optimized for performance, with extensive logging and error handling to facilitate debugging and maintenance.

The implementation adheres to:
- **PEP 8**: Python style guidelines for code readability and consistency.
- **Semantic Versioning (SemVer)**: Versioning scheme (e.g., `1.1.0`) to track changes systematically.
- **Keep a Changelog**: A structured changelog to document updates, fixes, and additions.

The current version of the system is `1.1.0`, reflecting optimizations and bug fixes from the initial deployment.

---

## System Overview

The camera streaming system operates as follows:
1. **Configuration Loading**: Reads a JSON configuration file (`/etc/roc/cameras.json`) containing IP addresses, usernames, and passwords for IP cameras.
2. **Camera Connectivity Testing**: Verifies camera reachability on RTMP port 1935 using socket connections.
3. **Stream Testing**: Tests available RTMP streams (`main`, `ext`, `sub`) for each camera using FFmpeg, selecting the highest-quality stream based on resolution, FPS, and frame duplication metrics.
4. **FFmpeg Streaming**: Launches FFmpeg processes to stream RTMP feeds to corresponding V4L2 loopback devices (e.g., `/dev/video0`).
5. **Monitoring and Recovery**: Continuously monitors FFmpeg processes, restarting failed streams with fallback to lower-quality stream types if necessary.
6. **Logging**: Maintains detailed logs in `/var/log/cameras/` and `/var/log/camera_streamer.log` for debugging and status tracking.

The system is headless, designed to run as a systemd service, and integrates with OBS Studio for video production workflows.

---

## Version History (Keep a Changelog)

### [1.1.0] - 2025-08-21

#### Added
- **FPS Stabilization**: Added `-vf fps=fps=<source_fps>` and `-vsync 1` to FFmpeg commands to enforce source frame rates and reduce duplicate frames.
- **Real-Time Streaming**: Included `-re` and `-rtmp_live live` in FFmpeg commands for real-time input and live streaming mode.
- **Camera Status Summary**: Added logging of a summary table for all cameras (IP, stream type, resolution, FPS, status) after initial setup.
- **Duplicate Frame Tracking**: Parse and log duplicate frame counts (`dup=X`) during stream testing.
- **Log Rotation Recommendation**: Suggested `logrotate` configuration for log file management.

#### Changed
- **Stream Test Timeout**: Increased `TEST_TIMEOUT` from 5 to 15 seconds to improve stream detection reliability.
- **Retry Logic**: Increased `MAX_RETRIES` from default to 12 (4 cycles through stream types) for robust error recovery.
- **Quality Scoring**: Modified quality score calculation to penalize duplicate frames (`1 - dup_count / 1000`).
- **Error Log Monitoring**: Updated `grep` pattern to include "end of file" for more comprehensive error capture.

#### Fixed
- **FPS Mismatch**: Addressed FPS overshooting (e.g., 13 fps for a 12 fps stream) with `-vf fps` and `-r <source_fps>`.
- **Duplicate Frames**: Reduced excessive frame duplication (e.g., `dup=137` for camera2) with `-vsync 1`.
- **Incomplete Camera Processing**: Ensured all cameras (e.g., 192.168.1.233, 192.168.1.68) are processed with status logged.

### [1.0.0] - 2025-08-01
#### Added
- Initial implementation of `camera_streamer.py` with support for RTMP streaming to V4L2 loopback devices.
- Basic stream testing and selection logic for `main`, `ext`, and `sub` streams.
- Logging to `/var/log/cameras/` and `/var/log/ffmpeg_errors.log`.
- Systemd service integration for headless operation.

#### Known Issues
- Stream failures for some cameras (e.g., 192.168.1.9, 192.168.1.174) due to "End of file" and "Input/output error".
- FPS instability (e.g., 13 fps for a 12 fps stream).
- Excessive duplicate frames (e.g., `dup=137` for camera2).
- Incomplete processing of some cameras (e.g., 192.168.1.233, 192.168.1.68).

---

## Code Explanation

The core implementation resides in `camera_streamer.py`, a Python script that follows PEP 8 guidelines for readability and maintainability. Below is a detailed breakdown of the code, provided within an artifact tag for clarity and reproducibility.

'''python
import os
import json
import subprocess
import logging
import sys
import time
import signal
import socket
import re

# Configuration
CAMERAS_CONFIG = '/etc/roc/cameras.json'
LOG_DIR = '/var/log/cameras'
ERROR_LOG = '/var/log/ffmpeg_errors.log'
SETUP_SCRIPT = '/usr/local/bin/setup_v4l2loopback.sh'
STREAM_TYPES = ['main', 'ext', 'sub']  # Order for quality preference
TEST_TIMEOUT = 15  # Increased timeout for stream testing
MAX_RETRIES = 12  # Increased retries (4 cycles through stream types)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/camera_streamer.log'),
        logging.StreamHandler()  # Centralized console output
    ]
)
logger = logging.getLogger(__name__)

class CameraStreamer:
    def __init__(self):
        self.processes = []
        self.exit_flag = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        logger.info(f"Received signal {sig}. Shutting down...")
        self.exit_flag = True
        for _, _, proc, _ in self.processes:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def test_camera_connection(self, ip, timeout=2):
        """Test if camera is reachable on RTMP port (1935)."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, 1935))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"Connection test to {ip}:1935 failed: {e}")
            return False

    def test_stream(self, ip, user, password, stream_type, channel=0, stream_num=0, timeout=TEST_TIMEOUT):
        """Test stream and extract resolution, FPS, and duplicate frames."""
        rtmp_url = f"rtmp://{ip}/bcs/channel{channel}_{stream_type}.bcs?channel={channel}&stream={stream_num}&user={user}&password={password}"
        cmd = [
            'ffmpeg',
            '-re',  # Real-time input
            '-rtmp_live', 'live',  # Force live streaming mode
            '-i', rtmp_url,
            '-t', '5',  # Short test duration
            '-f', 'null', '-'  # Output to null
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                # Parse resolution and FPS
                resolution_match = re.search(r'(\d+x\d+)', result.stderr)
                fps_match = re.search(r'(\d+\.?\d*) fps', result.stderr)
                dup_match = re.search(r'dup=(\d+)', result.stderr)
                resolution = resolution_match.group(1) if resolution_match else '0x0'
                width, height = map(int, resolution.split('x')) if resolution != '0x0' else (0, 0)
                fps = float(fps_match.group(1)) if fps_match else 0.0
                dup_count = int(dup_match.group(1)) if dup_match else 0
                quality_score = width * height * fps * (1 - dup_count / 1000)  # Penalize duplicates
                logger.info(f"Stream test succeeded for {ip} with {stream_type} stream: {resolution}@{fps}fps, dup={dup_count}, score={quality_score}")
                return True, resolution, fps, quality_score
            else:
                logger.warning(f"Stream test failed for {ip} with {stream_type} stream: {result.stderr}")
                return False, None, None, 0
        except subprocess.TimeoutExpired:
            logger.warning(f"Stream test timed out for {ip} with {stream_type} stream")
            return False, None, None, 0
        except Exception as e:
            logger.error(f"Stream test error for {ip} with {stream_type} stream: {e}")
            return False, None, None, 0

    def start_ffmpeg(self, i, cam, stream_type, fps):
        """Start FFmpeg with optimized settings."""
        ip = cam['ip']
        user = cam.get('user', 'admin')
        password = cam['password']
        channel = 0
        stream_num = 0 if stream_type in ['main', 'ext'] else 1

        rtmp_url = f"rtmp://{ip}/bcs/channel{channel}_{stream_type}.bcs?channel={channel}&stream={stream_num}&user={user}&password={password}"

        log_file = os.path.join(LOG_DIR, f"camera{i}.log")
        cmd = [
            'ffmpeg',
            '-re',  # Real-time input
            '-rtmp_live', 'live',  # Force live streaming mode
            '-i', rtmp_url,
            '-vf', f'fps=fps={fps}',  # Enforce source FPS
            '-vsync', '1',  # Variable frame rate syncing
            '-r', str(fps),  # Set output frame rate
            '-f', 'v4l2',
            f'/dev/video{i}'
        ]

        try:
            with open(log_file, 'a') as log:
                proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
            logger.info(f"Started ffmpeg for camera {i} ({ip}) on /dev/video{i} with {stream_type} stream (PID: {proc.pid})")
            return proc
        except Exception as e:
            logger.error(f"Failed to start ffmpeg for camera {i} ({ip}) with {stream_type} stream: {e}")
            return None

    def load_cameras_config(self):
        """Load camera configuration from JSON file."""
        if not os.path.exists(CAMERAS_CONFIG):
            logger.error(f"Config file {CAMERAS_CONFIG} not found.")
            sys.exit(1)

        try:
            with open(CAMERAS_CONFIG, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                if not content:
                    logger.error(f"Config file {CAMERAS_CONFIG} is empty.")
                    sys.exit(1)
                logger.debug(f"First 10 chars of {CAMERAS_CONFIG}: {repr(content[:10])}")
                cameras = json.loads(content)
                if not cameras:
                    logger.error(f"No cameras defined in {CAMERAS_CONFIG}.")
                    sys.exit(1)
                return cameras
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {CAMERAS_CONFIG}: {e}")
            with open(CAMERAS_CONFIG, 'r', encoding='utf-8-sig') as f:
                logger.error(f"File contents: {f.read()}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to read {CAMERAS_CONFIG}: {e}")
            sys.exit(1)

    def run(self):
        """Main loop to start and monitor FFmpeg processes."""
        os.makedirs(LOG_DIR, exist_ok=True)
        open(ERROR_LOG, 'w').close()

        # Run v4l2loopback setup script
        try:
            result = subprocess.run(SETUP_SCRIPT, shell=True, capture_output=True, text=True)
            logger.info(f"v4l2loopback setup completed: {result.stdout}")
            if result.returncode != 0:
                logger.error(f"Setup script error: {result.stderr}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to run setup script: {e}")
            sys.exit(1)

        # Verify v4l2loopback devices
        video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
        if not video_devices:
            logger.error("No v4l2loopback devices found in /dev. Check module loading.")
            sys.exit(1)
        logger.info(f"Found video devices: {', '.join(video_devices)}")

        # Load cameras config
        cameras = self.load_cameras_config()

        # Start FFmpeg processes for reachable cameras
        camera_status = []
        for i, cam in enumerate(cameras):
            if i >= 16:
                logger.warning("Maximum of 16 cameras supported. Ignoring additional cameras.")
                break
            if 'ip' not in cam or 'password' not in cam:
                logger.error(f"Invalid camera config at index {i}: missing ip or password")
                camera_status.append((i, cam['ip'], "skipped", "Invalid config"))
                continue
            if f"video{i}" not in video_devices:
                logger.error(f"/dev/video{i} not found. Skipping camera {cam['ip']}.")
                camera_status.append((i, cam['ip'], "skipped", "No v4l2 device"))
                continue
            if not self.test_camera_connection(cam['ip']):
                logger.error(f"Camera {cam['ip']} is not reachable on port 1935. Skipping.")
                camera_status.append((i, cam['ip'], "skipped", "Unreachable"))
                continue

            # Test all stream types and select the best based on quality
            user = cam.get('user', 'admin')
            password = cam['password']
            best_stream = None
            best_score = 0
            best_resolution = None
            best_fps = None

            for stream_type in STREAM_TYPES:
                stream_num = 0 if stream_type in ['main', 'ext'] else 1
                success, resolution, fps, quality_score = self.test_stream(
                    cam['ip'], user, password, stream_type, channel=0, stream_num=stream_num
                )
                if success and quality_score > best_score:
                    best_stream = stream_type
                    best_score = quality_score
                    best_resolution = resolution
                    best_fps = fps

            if not best_stream:
                logger.error(f"No valid stream (main, ext, sub) found for camera {cam['ip']}. Skipping.")
                camera_status.append((i, cam['ip'], "skipped", "No valid stream"))
                continue

            logger.info(f"Selected {best_stream} stream for camera {cam['ip']} ({best_resolution}@{best_fps}fps, score={best_score})")
            proc = self.start_ffmpeg(i, cam, best_stream, best_fps)
            if proc:
                self.processes.append((i, cam, proc, STREAM_TYPES.index(best_stream)))
                camera_status.append((i, cam['ip'], best_stream, f"{best_resolution}@{best_fps}fps"))
            else:
                camera_status.append((i, cam['ip'], "failed", "FFmpeg start failed"))

        # Log camera status summary
        logger.info("Camera setup summary:")
        for i, ip, stream, status in camera_status:
            logger.info(f"Camera {i} ({ip}): Stream={stream}, Status={status}")

        # Start error log monitoring
        subprocess.Popen([
            'bash', '-c',
            f'tail -f {os.path.join(LOG_DIR, "*.log")} | grep -iE "error|failed|timeout|connection refused|input/output error|end of file" >> {ERROR_LOG} &'
        ])

        # Monitor and restart FFmpeg processes with fallback
        retry_delay = 5
        while not self.exit_flag:
            time.sleep(1)
            for j, (i, cam, proc, fallback_index) in enumerate(self.processes):
                if proc and proc.poll() is not None:
                    logger.warning(f"ffmpeg for camera {i} ({cam['ip']}) with {STREAM_TYPES[fallback_index]} exited with code {proc.returncode}. Attempting fallback...")
                    next_index = (fallback_index + 1) % len(STREAM_TYPES)
                    retry_count = 0
                    best_stream = None
                    best_score = 0
                    best_resolution = None
                    best_fps = None

                    while retry_count < MAX_RETRIES:
                        if self.exit_flag:
                            break
                        if f"video{i}" not in [f for f in os.listdir('/dev') if f.startswith('video')]:
                            logger.error(f"/dev/video{i} no longer exists. Cannot restart camera {cam['ip']}.")
                            break
                        if not self.test_camera_connection(cam['ip']):
                            logger.error(f"Camera {cam['ip']} is not reachable on port 1935. Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 1.5, 30)
                            retry_count += 1
                            continue
                        next_stream = STREAM_TYPES[next_index]
                        stream_num = 0 if next_stream in ['main', 'ext'] else 1
                        user = cam.get('user', 'admin')
                        password = cam['password']
                        success, resolution, fps, quality_score = self.test_stream(
                            cam['ip'], user, password, next_stream, channel=0, stream_num=stream_num
                        )
                        if success and quality_score > best_score:
                            best_stream = next_stream
                            best_score = quality_score
                            best_resolution = resolution
                            best_fps = fps
                        next_index = (next_index + 1) % len(STREAM_TYPES)
                        retry_count += 1

                    if best_stream:
                        logger.info(f"Selected {best_stream} stream for camera {cam['ip']} ({best_resolution}@{best_fps}fps, score={best_score})")
                        new_proc = self.start_ffmpeg(i, cam, best_stream, best_fps)
                        if new_proc:
                            self.processes[j] = (i, cam, new_proc, STREAM_TYPES.index(best_stream))
                            retry_delay = 5
                    else:
                        logger.error(f"All streams failed for camera {cam['ip']}. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * 1.5, 30)

        logger.info("Cleaning up ffmpeg processes...")
        for _, _, proc, _ in self.processes:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

def main():
    streamer = CameraStreamer()
    streamer.run()

if __name__ == "__main__":
    main()

'''

### Dependencies and Configuration

The script relies on the following dependencies:
- **Python 3.8+**: For compatibility with modern Python features and libraries.
- **FFmpeg**: For handling RTMP streams and outputting to V4L2 devices.
- **V4L2 Loopback Module**: A modified version (referenced at [aab18011/v4l2loopback](https://github.com/aab18011/v4l2loopback)) to create virtual video devices.
- **Standard Python Libraries**: `os`, `json`, `subprocess`, `logging`, `sys`, `time`, `signal`, `socket`, `re`.

Configuration is managed via a JSON file located at `/etc/roc/cameras.json`, with the following structure:

```json
[
  {
    "ip": "192.168.1.110",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.142",
    "user": "admin",
    "password": "your-pass"
  },
  ...
]
```

Key configuration constants in the script:
- `CAMERAS_CONFIG`: Path to the JSON configuration file.
- `LOG_DIR`: Directory for per-camera FFmpeg logs (`/var/log/cameras/`).
- `ERROR_LOG`: Centralized FFmpeg error log (`/var/log/ffmpeg_errors.log`).
- `SETUP_SCRIPT`: Path to the V4L2 loopback setup script (`/usr/local/bin/setup_v4l2loopback.sh`).
- `STREAM_TYPES`: List of stream types (`main`, `ext`, `sub`) in order of preference.
- `TEST_TIMEOUT`: Timeout for stream testing (15 seconds).
- `MAX_RETRIES`: Maximum retry attempts for failed streams (12).

### Class Structure and Logic

The `CameraStreamer` class encapsulates the streaming logic:
- **Initialization** (`__init__`): Sets up an empty process list, an exit flag, and signal handlers for `SIGINT` and `SIGTERM` to ensure graceful shutdown.
- **Signal Handling** (`_signal_handler`): Terminates FFmpeg processes cleanly on interrupt or termination signals.
- **Camera Connectivity Testing** (`test_camera_connection`): Uses `socket` to check if the camera is reachable on RTMP port 1935.
- **Stream Testing** (`test_stream`): Runs a short FFmpeg test to extract resolution, FPS, and duplicate frame counts, calculating a quality score (`width * height * fps * (1 - dup_count / 1000)`).
- **FFmpeg Execution** (`start_ffmpeg`): Launches FFmpeg processes with optimized parameters to stream RTMP to V4L2 devices.
- **Configuration Loading** (`load_cameras_config`): Parses the JSON configuration file, handling errors like missing files or invalid JSON.
- **Main Loop** (`run`): Orchestrates the setup, stream selection, FFmpeg execution, and process monitoring with fallback logic.

The script follows a modular design, with each method focused on a single responsibility, adhering to PEP 8 naming conventions and docstrings.

### FFmpeg Command Optimization

The FFmpeg commands are optimized for stability and performance:
- **Input Options**:
  - `-re`: Ensures real-time reading of RTMP streams, reducing buffering delays.
  - `-rtmp_live live`: Forces live streaming mode to handle RTMP correctly.
- **Output Options**:
  - `-vf fps=fps=<source_fps>`: Enforces the source stream's frame rate to prevent overshooting (e.g., 13 fps for a 12 fps stream).
  - `-vsync 1`: Enables variable frame rate syncing to reduce duplicate frames.
  - `-r <source_fps>`: Sets the output frame rate to match V4L2 device expectations.
  - `-f v4l2`: Outputs to the V4L2 loopback device (e.g., `/dev/video0`).

The command structure is:
```bash
ffmpeg -re -rtmp_live live -i rtmp://<ip>/bcs/channel0_<stream_type>.bcs?channel=0&stream=<num>&user=<user>&password=<pass> -vf fps=fps=<fps> -vsync 1 -r <fps> -f v4l2 /dev/video<i>
```

### Error Handling and Logging

The script includes robust error handling and logging:
- **Error Handling**:
  - Checks for missing configuration files or invalid JSON.
  - Validates V4L2 device availability (`/dev/videoX`).
  - Tests camera connectivity before attempting streaming.
  - Implements retry logic with exponential backoff (5s to 30s) for failed streams.
  - Falls back to lower-quality streams (`main` → `ext` → `sub`) when necessary.
- **Logging**:
  - Logs to `/var/log/camera_streamer.log` for script-level events.
  - Per-camera FFmpeg logs in `/var/log/cameras/camera<i>.log`.
  - Centralized error log (`/var/log/ffmpeg_errors.log`) capturing errors like "timeout", "connection refused", "input/output error", and "end of file".
  - Summary table of camera statuses after initial setup.

Log rotation is recommended using `logrotate` to manage log file growth:
```bash
/var/log/cameras/*.log /var/log/camera_streamer.log /var/log/ffmpeg_errors.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
```

---

## Setup Process

### Prerequisites

1. **Operating System**: Ubuntu 20.04 or later (tested on 22.04).
2. **Dependencies**:
   - Python 3.8+: `sudo apt install python3 python3-pip`.
   - FFmpeg: `sudo apt install ffmpeg`.
   - V4L2 Loopback Module: A modified version must be installed (see [aab18011/v4l2loopback](https://github.com/aab18011/v4l2loopback)).
3. **Hardware**: A system with sufficient CPU and memory to handle multiple high-resolution streams (e.g., 4096x1248@20fps).
4. **Network**: Stable network connectivity to IP cameras on port 1935 (RTMP).

### Configuration File

Create `/etc/roc/cameras.json` with the camera details. Example:
```json
[
  {
    "ip": "192.168.1.110",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.142",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.103",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.9",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.174",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.233",
    "user": "admin",
    "password": "your-pass"
  },
  {
    "ip": "192.168.1.68",
    "user": "admin",
    "password": "your-pass"
  }
]
```

Ensure the file has appropriate permissions:
```bash
sudo mkdir -p /etc/roc
sudo chmod 644 /etc/roc/cameras.json
```

### Installation and Deployment

1. **Install the Script**:
   - Copy `camera_streamer.py` to `/usr/local/bin/`:
     ```bash
     sudo cp camera_streamer.py /usr/local/bin/
     sudo chmod +x /usr/local/bin/camera_streamer.py
     ```

2. **Create Log Directory**:
   ```bash
   sudo mkdir -p /var/log/cameras
   sudo chmod 755 /var/log/cameras
   ```

3. **Set Up Systemd Service**:
   - Create `/etc/systemd/system/camera-streamer.service`:
     ```bash
     [Unit]
     Description=Camera Streaming Service
     After=network.target

     [Service]
     ExecStart=/usr/local/bin/camera_streamer.py
     Restart=always
     User=root
     StandardOutput=syslog
     StandardError=syslog
     SyslogIdentifier=camera-streamer

     [Install]
     WantedBy=multi-user.target
     ```
   - Enable and start the service:
     ```bash
     sudo systemctl enable camera-streamer
     sudo systemctl start camera-streamer
     ```

4. **Set Up Log Rotation**:
   - Create `/etc/logrotate.d/camera_streamer`:
     ```bash
     /var/log/cameras/*.log /var/log/camera_streamer.log /var/log/ffmpeg_errors.log {
         daily
         rotate 7
         compress
         delaycompress
         missingok
         notifempty
         create 644 root root
     }
     ```
   - Test log rotation:
     ```bash
     sudo logrotate -f /etc/logrotate.d/camera_streamer
     ```

---

## Troubleshooting

### Common Issues and Resolutions

1. **Stream Failures ("End of file" or "Input/output error")**:
   - **Cause**: Network instability or camera firmware issues.
   - **Resolution**:
     - Verify camera connectivity: `ping <ip>` and `nc -zv <ip> 1935`.
     - Test RTMP streams directly: `ffplay rtmp://<ip>/bcs/channel0_main.bcs?channel=0&stream=0&user=admin&password=<pass>`.
     - Update camera firmware or check RTMP settings.
     - Increase `TEST_TIMEOUT` or `MAX_RETRIES` in the script if network latency is high.

2. **FPS Mismatch**:
   - **Cause**: FFmpeg buffering or incorrect frame rate handling.
   - **Resolution**:
     - Ensure `-vf fps=fps=<source_fps>` and `-vsync 1` are applied.
     - Monitor FPS in logs (`/var/log/cameras/camera<i>.log`).

3. **Duplicate Frames**:
   - **Cause**: FFmpeg not syncing frames correctly.
   - **Resolution**:
     - Verify `-vsync 1` and `-r <source_fps>` in FFmpeg commands.
     - Check logs for `dup=X` counts and adjust quality score penalty if necessary.

4. **Incomplete Camera Processing**:
   - **Cause**: Script crash or premature exit.
   - **Resolution**:
     - Check `/var/log/camera_streamer.log` for errors.
     - Ensure all cameras are listed in the status summary.
     - Increase `MAX_RETRIES` or add debug logging in the `run` method.

5. **V4L2 Device Errors**:
   - **Cause**: Missing or misconfigured V4L2 loopback devices.
   - **Resolution**:
     - Verify devices: `ls /dev/video*`.
     - Re-run the V4L2 setup script (`/usr/local/bin/setup_v4l2loopback.sh`).
     - Check [aab18011/v4l2loopback](https://github.com/aab18011/v4l2loopback) for setup details.

### Log Analysis

Key logs to monitor:
- **Script Log**: `/var/log/camera_streamer.log` for setup summary and high-level errors.
- **Per-Camera Logs**: `/var/log/cameras/camera<i>.log` for FFmpeg output (resolution, FPS, duplicates).
- **Error Log**: `/var/log/ffmpeg_errors.log` for FFmpeg-specific errors.

Example log entries:
```
2025-08-21 21:33:45,123 - INFO - Selected main stream for camera 192.168.1.110 (2560x1440@12.0fps, score=44236800.0)
2025-08-21 21:33:46,456 - WARNING - Stream test failed for 192.168.1.9 with main stream: End of file
2025-08-21 21:33:50,789 - INFO - Camera setup summary:
2025-08-21 21:33:50,790 - INFO - Camera 0 (192.168.1.110): Stream=main, Status=2560x1440@12.0fps
```

Analyze logs for:
- **Successful Streams**: Confirm resolution and FPS match camera capabilities.
- **Failures**: Look for "timeout", "connection refused", or "end of file".
- **Duplicates**: High `dup=X` values indicate syncing issues.

---

## Replication Instructions

To replicate the camera streaming system, follow these steps exactly. This ensures the system can be rebuilt in case of data loss.

### Step-by-Step Setup

1. **Prepare the Environment**:
   - Install Ubuntu 22.04 or later.
   - Install dependencies:
     ```bash
     sudo apt update
     sudo apt install python3 python3-pip ffmpeg
     ```

2. **Install V4L2 Loopback Module**:
   - Follow instructions at [aab18011/v4l2loopback](https://github.com/aab18011/v4l2loopback) to install and configure the modified V4L2 loopback module.
   - Verify devices: `ls /dev/video*`.

3. **Create Configuration File**:
   - Create `/etc/roc/cameras.json` with camera details (see [Configuration File](#configuration-file)).
   - Set permissions:
     ```bash
     sudo mkdir -p /etc/roc
     sudo chmod 644 /etc/roc/cameras.json
     ```

4. **Deploy the Script**:
   - Copy `camera_streamer.py` to `/usr/local/bin/`:
     ```bash
     sudo cp camera_streamer.py /usr/local/bin/
     sudo chmod +x /usr/local/bin/camera_streamer.py
     ```

5. **Set Up Log Directory**:
   ```bash
   sudo mkdir -p /var/log/cameras
   sudo chmod 755 /var/log/cameras
   ```

6. **Configure Systemd Service**:
   - Create `/etc/systemd/system/camera-streamer.service` (see [Installation and Deployment](#installation-and-deployment)).
   - Enable and start:
     ```bash
     sudo systemctl enable camera-streamer
     sudo systemctl start camera-streamer
     ```

7. **Set Up Log Rotation**:
   - Create `/etc/logrotate.d/camera_streamer` (see [Installation and Deployment](#installation-and-deployment)).
   - Test:
     ```bash
     sudo logrotate -f /etc/logrotate.d/camera_streamer
     ```

### Verification and Testing

1. **Check Service Status**:
   ```bash
   sudo systemctl status camera-streamer
   ```

2. **Monitor Logs**:
   ```bash
   tail -f /var/log/cameras/*.log /var/log/camera_streamer.log /var/log/ffmpeg_errors.log
   ```
   - Verify the camera setup summary includes all cameras.
   - Check for successful stream selections and stable FPS.

3. **Test V4L2 Devices**:
   - Use `ffplay` to verify each device:
     ```bash
     ffplay -f v4l2 -i /dev/video0
     ffplay -f v4l2 -i /dev/video1
     ```
   - Confirm smooth playback and correct resolution/FPS.

4. **Integrate with OBS Studio**:
   - Install OBS Studio (Flatpak recommended):
     ```bash
     flatpak install flathub com.obsproject.Studio
     ```
   - Grant permissions:
     ```bash
     flatpak override com.obsproject.Studio --device=all
     flatpak override com.obsproject.Studio --filesystem=host
     ```
   - Add V4L2 sources for each `/dev/video<i>` device, setting resolution and FPS from logs.
   - Disable buffering in OBS for real-time streaming.

5. **Test Camera Connectivity**:
   - Verify RTMP streams:
     ```bash
     ffplay rtmp://192.168.1.110/bcs/channel0_main.bcs?channel=0&stream=0&user=admin&password=your-pass
     ```
   - Check network connectivity:
     ```bash
     ping 192.168.1.110
     nc -zv 192.168.1.110 1935
     ```

6. **Monitor System Resources**:
   ```bash
   top
   ```
   - Ensure CPU and memory usage are within acceptable limits.
