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
