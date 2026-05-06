# core/video_decoder.py
import queue
import time
import os
import threading
import platform
import av
import numpy as np
from PySide6.QtCore import QThread

from core.frame_cache import FrameCache
from core.app_config import app_config
from core.signal_hub import global_signals
from core.logger import hive_logger

class VideoDecoder(QThread):
    """
    A high-performance, interruptible video decoding engine powered by PyAV.
    
    Implements a Producer-Consumer architecture with a non-blocking 'Seek Protocol'.
    Utilizes OS-native hardware acceleration (CUDA/VideoToolbox) and a multi-scale 
    LRU cache to provide a lag-free scrubbing experience.
    """

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.frame_queue = queue.Queue(maxsize=30)
        
        # Sync Protocol: Unique ID (nanosecond) to interrupt stale seek requests
        self._target_seek_id = 0
        self._current_seek_id = 0
        self._target_logical_pos = 0.0
        
        # Decoder State
        self.container = None
        self.video_stream = None
        self._render_scale = 1.0
        self._run_flag = True
        self.mutex = threading.Lock()
        
        # Initialize Cache (Shared memory budget from config)
        mem_mb = app_config.get_setting("playback_memory_limit", 1024)
        self.frame_cache = FrameCache(mem_mb * 1024 * 1024)
        
        # Listen for dynamic memory changes
        global_signals.memory_limit_changed.connect(self._on_memory_limit_changed)

    def _on_memory_limit_changed(self, new_limit_mb):
        if hasattr(self, 'frame_cache') and self.frame_cache:
            self.frame_cache.update_limit(new_limit_mb * 1024 * 1024)

    def set_scale(self, scale):
        """Updates the render scale for future decodes. Affects cache keys."""
        with self.mutex:
            self._render_scale = scale

    def seek_to(self, logical_pos):
        """
        Issues a prioritized seek request.
        Instantly invalidates current decoding via a new seek_id.
        """
        with self.mutex:
            self._target_logical_pos = logical_pos
            self._target_seek_id = time.time_ns()
            # Flush queue to make room for the new seek target frames
            while not self.frame_queue.empty():
                try: self.frame_queue.get_nowait()
                except queue.Empty: break

    def stop(self):
        """Gracefully shuts down the decoder thread and releases resources."""
        self._run_flag = False
        self.wait()

    def _setup_container(self):
        """Initializes PyAV container with hardware acceleration if available."""
        if self.container:
            self.container.close()
        
        try:
            # Hardware Acceleration Detection
            options = {'threads': 'auto'}
            hw_config = app_config.get_setting("hardware_acceleration_enabled", True)
            
            if hw_config:
                system = platform.system()
                if system == "Windows" or system == "Linux":
                    options['hwaccel'] = 'cuda' # NVDEC
                elif system == "Darwin":
                    options['hwaccel'] = 'videotoolbox'
            
            self.container = av.open(self.file_path, options=options)
            self.video_stream = self.container.streams.video[0]
            self.video_stream.thread_type = 'AUTO'
            
            hive_logger.info(f"VideoDecoder: Initialized {os.path.basename(self.file_path)} (HW: {hw_config})")
        except Exception as e:
            hive_logger.error(f"VideoDecoder: Init failed: {e}")
            self.container = av.open(self.file_path) # Fallback to SW
            self.video_stream = self.container.streams.video[0]

    def run(self):
        self._setup_container()
        
        while self._run_flag:
            try:
                with self.mutex:
                    target_ms = self._target_logical_pos * 10.0
                    active_seek_id = self._target_seek_id
                    current_scale = self._render_scale
                
                # Check for new seek request
                if active_seek_id != self._current_seek_id:
                    self._current_seek_id = active_seek_id
                    target_pts = int(target_ms / (float(self.video_stream.time_base) * 1000))
                    
                    # Optimization: Check Cache first
                    cached = self.frame_cache.get(target_pts, current_scale)
                    if cached is not None:
                        self.frame_queue.put((self._target_logical_pos, cached))
                        continue # Seek fulfilled from cache
                    
                    # Precise Seek: Jump to keyframe then fast-forward
                    self.container.seek(target_pts, backward=True, stream=self.video_stream)
                    
                    # FAST-FORWARD LOOP: Drain packets until target millisecond
                    for frame in self.container.decode(video=0):
                        # Interruption Check: Did a newer seek arrive during decoding?
                        if self._target_seek_id != active_seek_id:
                            break
                            
                        # Keep frames that are exactly at or slightly ahead of target
                        if (frame.time * 1000) < (target_ms - 1):
                            continue
                            
                        # Target reached - process and cache
                        sw = int(frame.width * current_scale)
                        sh = int(frame.height * current_scale)
                        
                        # High-speed YUV -> BGR24 conversion and Rescale
                        image = frame.to_ndarray(format='rgba', width=sw, height=sh)
                        
                        self.frame_cache.put(frame.pts, image, current_scale)
                        
                        # Push to UI queue (Mapping time to logical timeline units)
                        logical_out = (frame.time * 1000) / 10.0
                        self.frame_queue.put((logical_out, image))
                        
                        # Only push the first matching frame for a seek, then wait for next loop
                        break
                        
                else:
                    # Normal Playback / Background Pre-roll
                    # If queue is low, decode the next frame sequentially
                    if self.frame_queue.qsize() < 10:
                        try:
                            frame = next(self.container.decode(video=0))
                            
                            sw = int(frame.width * current_scale)
                            sh = int(frame.height * current_scale)
                            image = frame.to_ndarray(format='rgba', width=sw, height=sh)
                            
                            self.frame_cache.put(frame.pts, image, current_scale)
                            logical_out = (frame.time * 1000) / 10.0
                            self.frame_queue.put((logical_out, image))
                        except (StopIteration, av.error.FFmpegError):
                            # Loop or wait at EOF
                            time.sleep(0.01)
                    else:
                        time.sleep(0.005)

            except Exception as e:
                # Self-Healing recovery block: Prevent thread death on corrupt packets
                hive_logger.error(f"VideoDecoder: Loop Error: {e}")
                time.sleep(0.1)
                self._setup_container()
        
        if self.container:
            self.container.close()
        hive_logger.info("VideoDecoder: Thread stopped.")
l_path}: {error_msg}")
                                        self.pending_extractions.discard(f_hash)
                                        
                                    media_manager.start_audio_conform(
                                        clip.file_path, 
                                        on_finish_callback=on_audio_ready,
                                        on_fail_callback=on_audio_fail  
                                    )
                                continue

                            try:
                                new_track = AudioTrack(
                                    clip_id=clip.clip_id,
                                    file_path=target_audio_path,
                                    start_time_ms=start_ms,
                                    end_time_ms=end_ms,
                                    master_sample_rate=self.sample_rate,
                                    trim_in_ms=final_trim_in_ms # 3. SYNC FIX: Use the calculated trim
                                )
                                new_track.update_properties(vol_pct)
                                self.tracks[clip.clip_id] = new_track
                            except Exception as e:
                                hive_logger.error(f"AudioMixer Error loading {clip.clip_id}: {e}")
                                
            # Remove tracks that were deleted from the timeline
            # Cast keys to list to avoid runtime error during iteration deletion
            to_remove = [c_id for c_id in list(self.tracks.keys()) if c_id not in active_clip_ids]
            for c_id in to_remove:
                self.tracks[c_id].close()
                del self.tracks[c_id]
                
            # Keep playback synced to where the tracks moved
            current_playhead_ms = (self.current_frame / self.sample_rate) * 1000.0
            for track in self.tracks.values():
                track.seek_to_timeline_time(current_playhead_ms)

    def add_track(self, track):
        """Registers a newly created AudioTrack to the timeline."""
        with self.tracks_lock:
            # Insert into the dictionary properly using the clip_id
            self.tracks[track.clip_id] = track
        hive_logger.debug(f"Added track: {track.clip_id}")

    def clear_tracks(self):
        """Clears all tracks from the mixer when loading a new project."""
        with self.tracks_lock:
            for track in self.tracks.values(): 
                track.close()
            self.tracks.clear()

    def get_current_time_ms(self):
        """Returns the current timeline position in milliseconds, driven by the audio sample clock."""
        return (self.current_frame / self.sample_rate) * 1000.0

    def seek(self, playhead_ms):
        """
        When the user clicks somewhere on the UI timeline, we sync the mixer's internal 
        clock to that exact millisecond.
        """
        self.current_frame = int((playhead_ms / 1000.0) * self.sample_rate)
        
        with self.tracks_lock:
            for track in self.tracks.values(): 
                track.seek_to_timeline_time(playhead_ms)

    def _audio_callback(self, outdata, frames, time_info, status):
        """The C-level thread that runs hundreds of times a second."""
        if status:
            hive_logger.debug(f"Audio Status Warning: {status}")

        mixed_chunk = np.zeros((frames, self.channels), dtype=np.float32)

        if self.is_playing:
            current_ms = (self.current_frame / self.sample_rate) * 1000.0

            # Lock the thread and use .values() properly
            with self.tracks_lock:
                for track in self.tracks.values():
                    if track.is_active_at(current_ms):
                        
                        data = track.read_chunk(frames)
                        valid_frames = len(data)

                        if valid_frames > 0:
                            processed_data = data * track.volume

                            if processed_data.shape[1] == 1 and self.channels == 2:
                                processed_data = np.repeat(processed_data, 2, axis=1)

                            if self.channels == 2:
                                left_mult = max(0.0, 1.0 - track.pan)
                                right_mult = max(0.0, 1.0 + track.pan)
                                
                                processed_data[:, 0] *= left_mult 
                                processed_data[:, 1] *= right_mult
                            
                            mixed_chunk[:valid_frames] += processed_data

            self.current_frame += frames

        np.clip(mixed_chunk, -1.0, 1.0, out=mixed_chunk)

        outdata[:] = mixed_chunk

    def play(self):
        if self.stream is None:
            hive_logger.warning("AudioMixer: Cannot play, stream not initialized.")
            return
        self.is_playing = True
        if not self.stream.active:
            self.stream.start()

    def pause(self):
        self.is_playing = False

    def close(self):
        self.is_playing = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.clear_tracks()

# Global instance
audio_mixer = AudioMixer()
