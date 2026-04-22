# core/audio_mixer.py
import os
import hashlib
import numpy as np
import scipy.signal 
import threading
from pathlib import Path
import soundfile as sf
import sounddevice as sd

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
        Crucially, it calculates this based on the file's NATIVE sample rate, 
        even though the timeline operates on the MASTER sample rate.
        """
        if not self.is_active_at(playhead_ms):
            return

        elapsed_in_clip_ms = playhead_ms - self.start_time_ms
        total_offset_ms = elapsed_in_clip_ms + self.trim_in_ms
        
        # We MUST seek using the native sample rate of the file!
        target_frame = int((total_offset_ms / 1000.0) * self.native_sample_rate)
        
        self.audio_file.seek(target_frame)

    def read_chunk(self, required_master_frames):
        """
        Reads a chunk of audio, resampling it on the fly if the sample rates don't match.
        """
        if not self.needs_resampling:
            # Native match: Just read the exact frames requested by the mixer
            return self.audio_file.read(required_master_frames, always_2d=True)
        
        # Mismatch: We must read MORE or FEWER frames from the file, 
        # then stretch/squash them to exactly match the required_master_frames
        frames_to_read = int(required_master_frames * self.resample_ratio)
        native_data = self.audio_file.read(frames_to_read, always_2d=True)
        
        if len(native_data) == 0:
            return native_data
            
        # Use scipy to resample the audio array to perfectly fit the master mixer's request
        resampled_data = scipy.signal.resample(native_data, required_master_frames)
        return np.array(resampled_data, dtype=np.float32)

    def close(self):
        if not self.audio_file.closed:
            self.audio_file.close()

class AudioMixer:
    def __init__(self, sample_rate=44100, channels=2):
        """Initializes the Master Clock and Mixer Engine."""
        self.sample_rate = sample_rate
        self.channels = channels
        
        self.tracks = {}
        self.tracks_lock = threading.Lock()
        
        # Timeline Time Tracking
        self.is_playing = False
        self.current_frame = 0 
        
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            latency='high',
            blocksize=4096,
            callback=self._audio_callback
        )

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
                        trim_ms = clip.applied_effects.get("source_in", 0) * 10
                        vol_pct = float(clip.applied_effects.get("Volume", 100)) / 100.0
                        
                        if clip.clip_id in self.tracks:
                            # Update existing track directly (Trim/Move/Volume change)
                            self.tracks[clip.clip_id].update_timing(start_ms, end_ms, trim_ms)
                            self.tracks[clip.clip_id].update_properties(vol_pct)
                        else:
                            # Add newly dragged/cut clip

                            target_audio_path = clip.file_path
                            file_hash = hashlib.md5(clip.file_path.encode()).hexdigest()
                            conformed_path = Path.home() / ".hive_editor" / "audio_cache" / f"{file_hash}_conformed.wav"
                            
                            if conformed_path.exists():
                                target_audio_path = str(conformed_path)

                            try:
                                new_track = AudioTrack(
                                    clip_id=clip.clip_id,
                                    file_path=target_audio_path,
                                    start_time_ms=start_ms,
                                    end_time_ms=end_ms,
                                    master_sample_rate=self.sample_rate,
                                    trim_in_ms=trim_ms
                                )
                                new_track.update_properties(vol_pct)
                                self.tracks[clip.clip_id] = new_track
                            except Exception as e:
                                print(f"AudioMixer Error loading {clip.clip_id}: {e}")

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
            # FIX: Insert into the dictionary properly using the clip_id
            self.tracks[track.clip_id] = track
        print(f"Added track: {track.clip_id}")

    def clear_tracks(self):
        """Clears all tracks from the mixer when loading a new project."""
        with self.tracks_lock:
            for track in self.tracks.values(): 
                track.close()
            self.tracks.clear()

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
            print(f"Audio Status Warning: {status}")

        mixed_chunk = np.zeros((frames, self.channels), dtype=np.float32)

        if self.is_playing:
            current_ms = (self.current_frame / self.sample_rate) * 1000.0

            # FIX: Lock the thread and use .values() properly
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
        self.is_playing = True
        if not self.stream.active:
            self.stream.start()

    def pause(self):
        self.is_playing = False

    def close(self):
        self.is_playing = False
        self.stream.stop()
        self.stream.close()
        self.clear_tracks()