# core/video_decoder.py
import queue
import time
import os
import threading
import av
import numpy as np
from PySide6.QtCore import QThread

from core.frame_cache import FrameCache
from core.app_config import app_config
from core.signal_hub import global_signals
from core.logger import hive_logger

class VideoDecoder(QThread):
    """
    The Producer Thread: Bakes frames in the background using PyAV (Hardware Accelerated) 
    and places them on the warming rack (queue).
    """
    def __init__(self, file_path, buffer_size=30):
        super().__init__()
        self.file_path = file_path
        
        limit_mb = app_config.get_setting("playback_memory_limit", 1024)
        limit_bytes = limit_mb * 1024 * 1024
        self.frame_cache = FrameCache(max_memory_bytes=limit_bytes)
        global_signals.memory_limit_changed.connect(self._update_cache_limit)

        # This is our warming rack. maxsize=30 prevents us from eating up all your RAM.
        self.frame_queue = queue.Queue(maxsize=buffer_size)
        self._run_flag = True

        # Thread-Safety Locks
        self._seek_requested = False
        self._seek_target_ms = 0.0
        self._seek_lock = threading.Lock()
        
        # Hardware Acceleration Setup
        self.container = None
        self.video_stream = None
        self._setup_container()

    def _setup_container(self):
        """Initializes the PyAV container with optional Hardware Acceleration."""
        try:
            hw_enabled = app_config.get_setting("hardware_acceleration_enabled", True)
            selected_device = None
            
            if hw_enabled:
                os_name = app_config.get_setting("os", "Windows")
                if os_name in ["Windows", "Linux"]:
                    selected_device = "cuda" # NVDEC
                elif os_name == "Darwin":
                    selected_device = "videotoolbox"
            
            hwaccel = None
            if selected_device:
                try:
                    hwaccel = av.codec.hwaccel.HWAccel(device_type=selected_device)
                    hive_logger.info(f"VideoDecoder: Initializing with Hardware Acceleration ({selected_device}) for {os.path.basename(self.file_path)}")
                except Exception as e:
                    hive_logger.warning(f"VideoDecoder: Failed to initialize HWAccel {selected_device}: {e}")
            
            self.container = av.open(self.file_path, hwaccel=hwaccel)
            self.video_stream = self.container.streams.video[0]
            # Use multi-threading for software fallback if possible
            if not hwaccel:
                hive_logger.debug(f"VideoDecoder: Using software decoding for {os.path.basename(self.file_path)}")
                self.video_stream.thread_type = 'AUTO'
                
        except Exception as e:
            hive_logger.error(f"VideoDecoder: Critical error opening container for {self.file_path}: {e}")

    def _update_cache_limit(self, new_limit_mb):
        """Convert the new slider value to bytes and pass it to the cache."""
        new_limit_bytes = new_limit_mb * 1024 * 1024
        self.frame_cache.update_limit(new_limit_bytes)

    def stop(self):
        """Safely stops the thread and closes the video file."""
        self._run_flag = False
        self.wait()
        
        if self.container:
            self.container.close()

    def seek_to(self, logical_time):
        """Called when the user clicks somewhere new on the timeline."""
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

        with self._seek_lock:
            self._seek_requested = True
            # logical_time is in "10ms" units (matches H.I.V.E master clock)
            self._seek_target_ms = logical_time * 10.0

    def run(self):
        """The background loop that runs constantly while the video plays."""
        if not self.container or not self.video_stream:
            return

        # We use demux() and decode() to pull frames
        try:
            frame_generator = self.container.decode(video=0)
        except Exception as e:
            hive_logger.error(f"VideoDecoder: Failed to start decode generator for {os.path.basename(self.file_path)}: {e}")
            return

        while self._run_flag:
            # 1. Handle Seeks
            with self._seek_lock:
                if self._seek_requested:
                    try:
                        seek_start = time.time()
                        target_pts = int((self._seek_target_ms / 1000.0) / self.video_stream.time_base)
                        self.container.seek(target_pts, stream=self.video_stream)
                        frame_generator = self.container.decode(video=0)
                        seek_latency = (time.time() - seek_start) * 1000.0
                        hive_logger.debug(f"VideoDecoder: Seek latency for {os.path.basename(self.file_path)}: {seek_latency:.2f}ms")
                    except Exception as e:
                        hive_logger.warning(f"VideoDecoder: Seek failed for {os.path.basename(self.file_path)}: {e}")
                    self._seek_requested = False
                    continue
            
            # 2. Decode next frame if rack has space
            if not self.frame_queue.full():
                try:
                    frame = next(frame_generator)
                    
                    if frame:
                        # Convert PyAV frame to NumPy BGR for the rest of the H.I.V.E engine
                        # This maintains compatibility with OpenCV effects in RenderEngine
                        img_bgr = frame.to_ndarray(format='bgr24')
                        
                        # Calculate logical position (10ms units)
                        logical_pos = (frame.time * 1000.0) / 10.0
                        
                        # Put on the rack!
                        self.frame_queue.put((logical_pos, img_bgr))
                        
                except (StopIteration, av.AVError):
                    # End of file or error, wait a bit
                    time.sleep(0.05)
                except Exception as e:
                    # Specific handling for packet errors
                    hive_logger.debug(f"VideoDecoder: Decoding error in {os.path.basename(self.file_path)}: {e}")
                    time.sleep(0.05)
            else:
                # Rack is full, chill for a bit
                time.sleep(0.01)