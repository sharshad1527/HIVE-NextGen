# core/media_manager.py

import os
import hashlib
import subprocess
import re
import struct
import json
from collections import deque
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
        if self.json_path.exists():
            try:
                with open(self.json_path, 'r') as f:
                    data = json.load(f)
                    self.waveform_ready.emit(self.file_path, data)
                return
            except Exception:
                pass

        cmd = [
            "ffmpeg", "-y", "-i", self.file_path,
            "-vn", "-ac", "1", "-ar", "800", "-f", "s16le", "-"
        ]
        
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)
            raw_data, _ = process.communicate()
            
            if not raw_data:
                self.waveform_ready.emit(self.file_path, [])
                return

            count = len(raw_data) // 2
            samples = struct.unpack(f"<{count}h", raw_data)
            
            chunk_size = 16 
            peaks = []
            for i in range(0, len(samples), chunk_size):
                chunk = samples[i:i+chunk_size]
                if chunk:
                    peaks.append(max(abs(s) for s in chunk))
            
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
    progress_updated = Signal(str, int)  
    proxy_finished = Signal(str, str)    
    proxy_failed = Signal(str, str)      

    def __init__(self, file_path, cache_dir):
        super().__init__()
        self.file_path = file_path
        self.cache_dir = Path(cache_dir)
        
        file_hash = hashlib.md5(file_path.encode()).hexdigest()
        self.proxy_path = str(self.cache_dir / f"{file_hash}_proxy.mp4")

    def get_video_duration(self, file_path):
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _get_hw_encoder(self):
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, **kwargs)
            output = result.stdout.lower()
            
            if "h264_nvenc" in output: return "h264_nvenc"             
            if "h264_videotoolbox" in output: return "h264_videotoolbox" 
            if "h264_amf" in output: return "h264_amf"               
            if "h264_qsv" in output: return "h264_qsv"               
        except Exception as e:
            print(f"Could not probe FFmpeg encoders: {e}")
        return None

    def _execute_ffmpeg(self, cmd, total_duration):
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, **kwargs)
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
        if os.path.exists(self.proxy_path):
            self.progress_updated.emit(self.file_path, 100)
            self.proxy_finished.emit(self.file_path, self.proxy_path)
            return

        total_duration = self.get_video_duration(self.file_path)
        if total_duration <= 0:
            self.proxy_failed.emit(self.file_path, "Could not determine video duration. FFmpeg may not be installed.")
            return

        res_setting = app_config.get_setting("proxy_resolution", "360p")
        height = res_setting.replace("p", "")
        hw_enabled = app_config.get_setting("hardware_acceleration", True)

        encoder = "libx264"
        preset_args = ["-preset", "ultrafast", "-crf", "28"]
        
        if hw_enabled:
            hw_enc = self._get_hw_encoder()
            if hw_enc:
                encoder = hw_enc
                if encoder == "h264_nvenc":
                    preset_args = ["-preset", "p1", "-cq", "28"] 
                elif encoder == "h264_videotoolbox":
                    preset_args = ["-q:v", "50"] 
                elif encoder in ["h264_amf", "h264_qsv"]:
                    preset_args = ["-preset", "fast", "-q:v", "28"] 

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

        if success:
            self.progress_updated.emit(self.file_path, 100)
            self.proxy_finished.emit(self.file_path, self.proxy_path)
        else:
            self.proxy_failed.emit(self.file_path, "FFmpeg failed to generate proxy on both GPU and CPU.")


class MediaManager:
    """Handles parsing files, extracting metadata, generating thumbnails, and proxy queues."""
    
    def __init__(self):
        self.config_dir = Path.home() / ".hive_editor"
        self.thumb_dir = self.config_dir / "thumbnails"
        self.proxy_dir = self.config_dir / "proxies" 
        
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_dir.mkdir(parents=True, exist_ok=True)
        
        self.proxy_queue = deque()
        self.active_proxy_threads = set()
        self.max_concurrent_proxies = 2 # Strictly enforces limit to protect OS resources

    def process_file(self, file_path):
        if not os.path.exists(file_path):
            return None
            
        ext = os.path.splitext(file_path)[1].lower()
        
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

        thumb_path = None
        if media_type == 'image':
            thumb_path = file_path 
        elif media_type == 'video':
            file_hash = hashlib.md5(file_path.encode()).hexdigest()
            thumb_path = str(self.thumb_dir / f"{file_hash}.jpg")
            
            if not os.path.exists(thumb_path):
                try:
                    import cv2
                    cap = cv2.VideoCapture(file_path)
                    ret, frame = cap.read()
                    if ret:
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
        """Pushes a heavy video proxy request into the queue."""
        task = {
            "file_path": file_path,
            "on_progress_callback": on_progress_callback,
            "on_finish_callback": on_finish_callback,
            "on_fail_callback": on_fail_callback
        }
        self.proxy_queue.append(task)
        self._process_next_proxy()

    def _process_next_proxy(self):
        """Spawns the worker thread if we are beneath the CPU resource cap."""
        if len(self.active_proxy_threads) >= self.max_concurrent_proxies:
            return
            
        if not self.proxy_queue:
            return
            
        task = self.proxy_queue.popleft()
        
        if "on_progress_callback" in task:
            thread = ProxyGeneratorThread(task["file_path"], self.proxy_dir)
            self.active_proxy_threads.add(thread)
            
            if task.get("on_progress_callback"):
                thread.progress_updated.connect(task["on_progress_callback"])
            if task.get("on_finish_callback"):
                thread.proxy_finished.connect(task["on_finish_callback"])
            if task.get("on_fail_callback"):
                thread.proxy_failed.connect(task["on_fail_callback"])
                
            thread.finished.connect(lambda t=thread: self._on_proxy_thread_finished(t))
            thread.finished.connect(thread.deleteLater)
            thread.start()
        else:
            thread = WaveformGeneratorThread(task["file_path"], app_config.waveform_cache_path)
            self.active_proxy_threads.add(thread) 
            thread.waveform_ready.connect(self._on_waveform_ready)
            thread.finished.connect(lambda t=thread: self._on_proxy_thread_finished(t))
            thread.finished.connect(thread.deleteLater)
            thread.start()

    def _on_proxy_thread_finished(self, thread):
        """Releases the thread from the resource pool and triggers the next item in the queue."""
        if thread in self.active_proxy_threads:
            self.active_proxy_threads.discard(thread)
        self._process_next_proxy()

    def request_waveform(self, file_path):
        if not os.path.exists(file_path):
            return
            
        task = {
            "file_path": file_path
        }
        self.proxy_queue.append(task)
        self._process_next_proxy()

    def _on_waveform_ready(self, file_path, data):
        from core.signal_hub import global_signals
        global_signals.waveform_ready.emit(file_path, data)

media_manager = MediaManager()