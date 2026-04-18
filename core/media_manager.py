# core/media_manager.py

import os
import hashlib
import subprocess
import re
import struct
import json
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.app_config import app_config

class WaveformGeneratorThread(QThread):
    """Background thread to extract audio peak envelopes cleanly using FFmpeg."""
    waveform_ready = Signal(str, list)

    def __init__(self, file_path, cache_dir):
        super().__init__()
        self.file_path = file_path
        self.cache_dir = Path(cache_dir)
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        self.json_path = self.cache_dir / f"{file_hash}_wave.json"

    def run(self):
        # 1. Attempt to load from JSON cache if it already exists
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r') as f:
                    data = json.load(f)
                    self.waveform_ready.emit(self.file_path, data)
                return
            except Exception:
                pass

        # 2. Extract mono, 800 Hz, 16-bit PCM using FFmpeg. 
        # Downsampling to 800Hz directly saves extreme amounts of memory/CPU for long files.
        cmd = [
            "ffmpeg", "-y", "-i", self.file_path,
            "-vn", "-ac", "1", "-ar", "800", "-f", "s16le", "-"
        ]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            raw_data, _ = process.communicate()
            
            if not raw_data:
                self.waveform_ready.emit(self.file_path, [])
                return

            count = len(raw_data) // 2
            samples = struct.unpack(f"<{count}h", raw_data)
            
            # For ~50 visual peaks per second at 800 Hz: chunk by 16 samples.
            chunk_size = 16 
            peaks = []
            for i in range(0, len(samples), chunk_size):
                chunk = samples[i:i+chunk_size]
                if chunk:
                    peaks.append(max(abs(s) for s in chunk))
            
            # Normalize height strictly between 0 and 100 for the UI
            max_peak = max(peaks) if peaks else 1
            if max_peak == 0: max_peak = 1
            normalized = [int((p / max_peak) * 100) for p in peaks]
            
            with open(self.json_path, 'w') as f:
                json.dump(normalized, f)
                
            self.waveform_ready.emit(self.file_path, normalized)
            
        except Exception as e:
            print(f"Waveform generation failed: {e}")
            self.waveform_ready.emit(self.file_path, [])


class ProxyGeneratorThread(QThread):
    """Background thread to transcode 4K/Heavy videos to 360p proxies using FFmpeg."""
    progress_updated = Signal(str, int)  # file_path, percentage (0-100)
    proxy_finished = Signal(str, str)    # original_path, proxy_path
    proxy_failed = Signal(str, str)      # original_path, error_message

    def __init__(self, file_path, cache_dir):
        super().__init__()
        self.file_path = file_path
        self.cache_dir = Path(cache_dir)
        
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        self.proxy_path = str(self.cache_dir / f"{file_hash}_proxy.mp4")

    def get_video_duration(self, file_path):
        """Uses ffprobe to get the exact duration of the video in seconds."""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _get_hw_encoder(self):
        """Queries FFmpeg to find available hardware encoders on the host machine."""
        try:
            result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
            output = result.stdout.lower()
            
            if "h264_nvenc" in output: return "h264_nvenc"             # NVIDIA
            if "h264_videotoolbox" in output: return "h264_videotoolbox" # Mac Silicon
            if "h264_amf" in output: return "h264_amf"               # AMD
            if "h264_qsv" in output: return "h264_qsv"               # Intel QuickSync
        except Exception as e:
            print(f"Could not probe FFmpeg encoders: {e}")
            
        return None

    def _execute_ffmpeg(self, cmd, total_duration):
        """Runs the FFmpeg command, parses progress, and returns True if successful."""
        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)")

            for line in process.stderr:
                match = time_regex.search(line)
                if match:
                    hours = float(match.group(1))
                    mins = float(match.group(2))
                    secs = float(match.group(3))
                    
                    current_seconds = (hours * 3600) + (mins * 60) + secs
                    percentage = int((current_seconds / total_duration) * 100)
                    
                    percentage = max(0, min(100, percentage))
                    self.progress_updated.emit(self.file_path, percentage)

            process.wait()
            return process.returncode == 0 and os.path.exists(self.proxy_path)
        except Exception as e:
            print(f"FFmpeg execution error: {e}")
            return False

    def run(self):
        # Skip if proxy already exists
        if os.path.exists(self.proxy_path):
            self.progress_updated.emit(self.file_path, 100)
            self.proxy_finished.emit(self.file_path, self.proxy_path)
            return

        total_duration = self.get_video_duration(self.file_path)
        if total_duration <= 0:
            self.proxy_failed.emit(self.file_path, "Could not determine video duration. FFmpeg may not be installed.")
            return

        # Read settings from config
        res_setting = app_config.get_setting("proxy_resolution", "360p")
        height = res_setting.replace("p", "")
        hw_enabled = app_config.get_setting("hardware_acceleration", True)

        encoder = "libx264"
        preset_args = ["-preset", "ultrafast", "-crf", "28"]
        
        # 1. Determine HW Encoder if enabled
        if hw_enabled:
            hw_enc = self._get_hw_encoder()
            if hw_enc:
                encoder = hw_enc
                if encoder == "h264_nvenc":
                    preset_args = ["-preset", "p1", "-cq", "28"] # NVIDIA fastest preset
                elif encoder == "h264_videotoolbox":
                    preset_args = ["-q:v", "50"] # Mac Hardware
                elif encoder in ["h264_amf", "h264_qsv"]:
                    preset_args = ["-preset", "fast", "-q:v", "28"] # AMD/Intel

        # 2. Build initial command
        cmd = [
            "ffmpeg", "-y", 
            "-i", self.file_path,
            "-vf", f"scale=-2:{height}",
            "-c:v", encoder,
            *preset_args,
            "-c:a", "aac", "-b:a", "128k",
            self.proxy_path
        ]

        print(f"Proxy Thread: Attempting to generate proxy using '{encoder}'...")
        success = self._execute_ffmpeg(cmd, total_duration)

        # 3. SMART FALLBACK: If hardware acceleration fails, seamlessly retry with CPU
        if not success and encoder != "libx264":
            print(f"Proxy Thread: Hardware Encoder '{encoder}' failed! Falling back to CPU (libx264)...")
            
            cmd = [
                "ffmpeg", "-y", 
                "-i", self.file_path,
                "-vf", f"scale=-2:{height}",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac", "-b:a", "128k",
                self.proxy_path
            ]
            success = self._execute_ffmpeg(cmd, total_duration)

        # 4. Final signal dispatch
        if success:
            self.progress_updated.emit(self.file_path, 100)
            self.proxy_finished.emit(self.file_path, self.proxy_path)
        else:
            self.proxy_failed.emit(self.file_path, "FFmpeg failed to generate proxy on both GPU and CPU.")


class MediaManager:
    """Handles parsing files, extracting metadata, generating thumbnails, and proxy queues."""
    
    def __init__(self):
        # We rely on the core ~/.hive_editor folders
        self.config_dir = Path.home() / ".hive_editor"
        self.thumb_dir = self.config_dir / "thumbnails"
        self.proxy_dir = self.config_dir / "proxies" 
        
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_dir.mkdir(parents=True, exist_ok=True)
        
        # Keep references to threads so PySide6 doesn't destroy them
        self.active_proxy_threads = set()

    def process_file(self, file_path):
        """Analyzes a file and returns UI-ready metadata and a thumbnail."""
        if not os.path.exists(file_path):
            return None
            
        ext = os.path.splitext(file_path)[1].lower()
        
        # Categorize
        if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
            media_type = 'video'
            icon = 'mdi6.movie-open-outline'
        elif ext in ['.wav', '.mp3', '.aac', '.flac']:
            media_type = 'audio'
            icon = 'mdi6.music-note-outline'
        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            media_type = 'image'
            icon = 'mdi6.image-outline'
        else:
            media_type = 'unknown'
            icon = 'mdi6.file-outline'

        # Generate Thumbnail (Images and Videos)
        thumb_path = None
        if media_type == 'image':
            thumb_path = file_path # Direct path for images
        elif media_type == 'video':
            # Hash the path so we only generate the thumbnail once
            file_hash = hashlib.md5(file_path.encode()).hexdigest()
            thumb_path = str(self.thumb_dir / f"{file_hash}.jpg")
            
            if not os.path.exists(thumb_path):
                try:
                    import cv2
                    cap = cv2.VideoCapture(file_path)
                    ret, frame = cap.read()
                    if ret:
                        # Resize to make it extremely lightweight for the UI
                        frame = cv2.resize(frame, (145, 80))
                        cv2.imwrite(thumb_path, frame)
                    cap.release()
                except ImportError:
                    print("OpenCV (cv2) not installed. Skipping video thumbnail generation.")
                    thumb_path = None
                except Exception as e:
                    print(f"Failed to generate thumbnail for {file_path}: {e}")
                    thumb_path = None

        return {
            "path": file_path,
            "name": os.path.basename(file_path),
            "type": media_type,
            "icon": icon,
            "thumbnail": thumb_path
        }

    def start_proxy_generation(self, file_path, on_progress_callback, on_finish_callback, on_fail_callback=None):
        """Spawns the worker thread to transcode a heavy video to proxy format."""
        thread = ProxyGeneratorThread(file_path, self.proxy_dir)
        self.active_proxy_threads.add(thread)
        
        # Connect signals
        if on_progress_callback:
            thread.progress_updated.connect(on_progress_callback)
        if on_finish_callback:
            thread.proxy_finished.connect(on_finish_callback)
        if on_fail_callback:
            thread.proxy_failed.connect(on_fail_callback)
            
        # Cleanup when done
        thread.finished.connect(lambda t=thread: self.active_proxy_threads.discard(t) if t in self.active_proxy_threads else None)
        thread.finished.connect(thread.deleteLater)
        
        thread.start()

    def request_waveform(self, file_path):
        """Asynchronously requests waveform envelope data for an audio/video file."""
        if not os.path.exists(file_path):
            return
            
        thread = WaveformGeneratorThread(file_path, app_config.waveform_cache_path)
        self.active_proxy_threads.add(thread)
        thread.waveform_ready.connect(self._on_waveform_ready)
        thread.finished.connect(lambda t=thread: self.active_proxy_threads.discard(t) if t in self.active_proxy_threads else None)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_waveform_ready(self, file_path, data):
        from core.signal_hub import global_signals
        global_signals.waveform_ready.emit(file_path, data)

# Global singleton
media_manager = MediaManager()