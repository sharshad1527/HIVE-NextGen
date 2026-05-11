# core/audio_mixer.py
import os
import hashlib
import numpy as np
import threading
import time
from pathlib import Path
import soundfile as sf
import sounddevice as sd
from core.logger import hive_logger

class LinearInterpolator:
    @staticmethod
    def resample(data, original_sr, target_sr, target_frames):
        if len(data) == 0:
            return data
        
        original_frames = len(data)
        x_old = np.linspace(0, original_frames - 1, original_frames)
        x_new = np.linspace(0, original_frames - 1, target_frames)
        
        channels = data.shape[1]
        resampled_data = np.zeros((target_frames, channels), dtype=np.float32)
        
        for c in range(channels):
            resampled_data[:, c] = np.interp(x_new, x_old, data[:, c])
            
        return resampled_data

class RingBuffer:
    def __init__(self, capacity, channels):
        self.capacity = capacity
        self.channels = channels
        self.buffer = np.zeros((capacity, channels), dtype=np.float32)
        self.write_ptr = 0
        self.read_ptr = 0
        self.size = 0
        self.lock = threading.Lock()
        
    def push(self, data):
        frames = len(data)
        if frames == 0:
            return 0
            
        with self.lock:
            frames_to_write = min(frames, self.capacity - self.size)
            if frames_to_write < frames:
                data = data[:frames_to_write]
                
            end_idx = self.write_ptr + frames_to_write
            if end_idx <= self.capacity:
                self.buffer[self.write_ptr:end_idx] = data
            else:
                first_part = self.capacity - self.write_ptr
                second_part = frames_to_write - first_part
                self.buffer[self.write_ptr:] = data[:first_part]
                self.buffer[:second_part] = data[first_part:]
                
            self.write_ptr = (self.write_ptr + frames_to_write) % self.capacity
            self.size += frames_to_write
            return frames_to_write

    def pop(self, frames):
        with self.lock:
            frames_to_read = min(frames, self.size)
            if frames_to_read == 0:
                return np.zeros((0, self.channels), dtype=np.float32)
                
            end_idx = self.read_ptr + frames_to_read
            out_data = np.zeros((frames_to_read, self.channels), dtype=np.float32)
            
            if end_idx <= self.capacity:
                out_data[:] = self.buffer[self.read_ptr:end_idx]
            else:
                first_part = self.capacity - self.read_ptr
                second_part = frames_to_read - first_part
                out_data[:first_part] = self.buffer[self.read_ptr:]
                out_data[first_part:] = self.buffer[:second_part]
                
            self.read_ptr = (self.read_ptr + frames_to_read) % self.capacity
            self.size -= frames_to_read
            return out_data
            
    def clear(self):
        with self.lock:
            self.write_ptr = 0
            self.read_ptr = 0
            self.size = 0

class AudioTrack:
    """Represents a single audio clip mapped to specific times on the timeline."""
    def __init__(self, clip_id, file_path, start_time_ms, end_time_ms, master_sample_rate, trim_in_ms=0.0):
        self.clip_id = clip_id
        self.file_path = file_path
        self.audio_file = sf.SoundFile(file_path)

        # Timeline placement
        self.start_time_ms = start_time_ms
        self.end_time_ms = end_time_ms
        self.trim_in_ms = trim_in_ms

        # Dynamic properties
        self.volume = 1.0
        self.pan = 0.0

        # --- SAMPLE RATE HANDLING ---
        self.master_sample_rate = master_sample_rate
        self.native_sample_rate = self.audio_file.samplerate
        self.channels = self.audio_file.channels

        # Flag to check if we need to mathematically stretch/squash the audio chunks
        self.needs_resampling = (self.native_sample_rate != self.master_sample_rate)

        # Calculate the ratio (e.g., 48000 / 44100 = ~1.088)
        self.resample_ratio = self.native_sample_rate / self.master_sample_rate

        # --- BACKGROUND BUFFERING ---
        # 1 second buffer at master sample rate
        self.buffer = RingBuffer(master_sample_rate, self.channels)
        self._stop_event = threading.Event()
        self._seek_request = None
        self._seek_lock = threading.Lock()
        
        self.worker_thread = threading.Thread(target=self._fill_buffer_thread, daemon=True)
        self.worker_thread.start()

    def _fill_buffer_thread(self):
        # Read chunks of ~0.1s
        chunk_size = int(self.master_sample_rate * 0.1)
        
        while not self._stop_event.is_set():
            # Handle seek
            with self._seek_lock:
                if self._seek_request is not None:
                    try:
                        self.audio_file.seek(self._seek_request)
                    except Exception as e:
                        hive_logger.error(f"Error seeking audio file {self.file_path}: {e}")
                    self.buffer.clear()
                    self._seek_request = None
            
            # If buffer is almost full, sleep and wait
            if self.buffer.capacity - self.buffer.size < chunk_size:
                time.sleep(0.01)
                continue
                
            # Read from disk
            try:
                frames_to_read = int(chunk_size * self.resample_ratio) if self.needs_resampling else chunk_size
                native_data = self.audio_file.read(frames_to_read, always_2d=True)
                
                if len(native_data) > 0:
                    if self.needs_resampling:
                        processed_data = LinearInterpolator.resample(
                            native_data, 
                            self.native_sample_rate, 
                            self.master_sample_rate, 
                            chunk_size
                        )
                    else:
                        processed_data = np.array(native_data, dtype=np.float32)
                        
                    self.buffer.push(processed_data)
                else:
                    # EOF, sleep a bit to prevent spinning
                    time.sleep(0.05)
            except Exception as e:
                hive_logger.error(f"Error reading audio file {self.file_path}: {e}")
                time.sleep(0.1)

    def update_timing(self, start_time_ms, end_time_ms, trim_in_ms):
        self.start_time_ms = start_time_ms
        self.end_time_ms = end_time_ms
        self.trim_in_ms = trim_in_ms

    def update_properties(self, volume, pan=0.0):
        self.volume = volume
        self.pan = pan

    def is_active_at(self, playhead_ms):
        """Checks if the master playhead is currently over this clip."""
        return self.start_time_ms <= playhead_ms < self.end_time_ms

    def seek_to_timeline_time(self, playhead_ms):
        """
        Calculates exactly where the file pointer needs to be.
        """
        if not self.is_active_at(playhead_ms):
            return

        elapsed_in_clip_ms = playhead_ms - self.start_time_ms
        total_offset_ms = elapsed_in_clip_ms + self.trim_in_ms

        target_frame = int((total_offset_ms / 1000.0) * self.native_sample_rate)

        with self._seek_lock:
            self._seek_request = target_frame

    def read_chunk(self, required_master_frames):
        """
        Pops a chunk of audio from the background buffer.
        """
        return self.buffer.pop(required_master_frames)

    def close(self):
        self._stop_event.set()
        if hasattr(self, 'worker_thread') and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=0.5)
            
        if not self.audio_file.closed:
            self.audio_file.close()

class AudioMixer:
    def __init__(self, sample_rate=44100, channels=2):
        """Initializes the Master Clock and Mixer Engine."""
        self.sample_rate = sample_rate
        self.channels = channels

        self.tracks = {}
        self.tracks_lock = threading.Lock()
        self.pending_extractions = set()

        # Timeline Time Tracking
        self.is_playing = False
        self.current_frame = 0
        self.stream = None

    def initialize(self):
        """Starts the audio output stream. Deferring this prevents blocking during startup."""
        if self.stream is not None:
            return

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            latency='high',
            blocksize=4096,
            callback=self._audio_callback
        )
        hive_logger.info(f"AudioMixer initialized (SR: {self.sample_rate}, Channels: {self.channels})")   

    def sync_from_project(self, project):
        """Diffs the current timeline state and intelligently updates tracks."""
        if not project: return

        active_clip_ids = set()

        with self.tracks_lock:
            for track in project.tracks:
                if getattr(track, 'is_hidden', False) or getattr(track, 'is_muted', False):
                    continue # Ignore hidden tracks completely

                for clip in track.clips:
                    if clip.clip_type in ["audio", "video"] and clip.file_path:
                        active_clip_ids.add(clip.clip_id)

                        start_ms = clip.start_time
                        end_ms = clip.end_time

                        trim_in_ms = getattr(clip, 'trim_in', 0)
                        fx_source_in = clip.applied_effects.get("source_in", 0) * 10
                        final_trim_in_ms = max(trim_in_ms, fx_source_in)

                        vol_pct = float(clip.applied_effects.get("Volume", 100)) / 100.0

                        if clip.clip_id in self.tracks:
                            # Update existing track directly (Trim/Move/Volume change)
                            self.tracks[clip.clip_id].update_timing(start_ms, end_ms, final_trim_in_ms)   
                            self.tracks[clip.clip_id].update_properties(vol_pct)
                        else:
                            # Add newly dragged/cut clip
                            # 1. Standardize path and hash by FILE, not clip ID
                            normalized_path = clip.file_path.replace('\\', '/')
                            file_hash = hashlib.md5(normalized_path.encode()).hexdigest()
                            conformed_path = Path.home() / ".hive_editor" / "audio_cache" / f"{file_hash}_conformed.wav"
                            target_audio_path = clip.file_path

                            if conformed_path.exists():
                                target_audio_path = str(conformed_path)
                            elif clip.clip_type == "video":
                                # 2. SPAM GUARD: Check the FILE HASH, not the clip ID
                                if file_hash not in self.pending_extractions:
                                    hive_logger.info(f"Extracting audio for {clip.file_path}...")
                                    self.pending_extractions.add(file_hash)

                                    from core.media_manager import media_manager

                                    def on_audio_ready(original_path, wav_path, f_hash=file_hash):        
                                        hive_logger.info(f"Extraction complete for {original_path}! Resyncing mixer...")
                                        self.pending_extractions.discard(f_hash)
                                        self.sync_from_project(project)

                                    def on_audio_fail(original_path, error_msg, f_hash=file_hash):        
                                        hive_logger.error(f"Extraction FAILED for {original_path}: {error_msg}")
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
