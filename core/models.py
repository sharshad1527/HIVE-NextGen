#core/models.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import uuid
from enum import Enum
import copy
import math

class Easing(Enum):
    LINEAR = 0
    EASE_IN = 1
    EASE_OUT = 2
    EASE_IN_OUT = 3
    BOUNCE = 4
    ELASTIC = 5
    CUBIC_IN = 6
    CUBIC_OUT = 7

@dataclass
class Keyframe:
    time: float
    value: float
    easing: Easing = Easing.LINEAR

@dataclass
class AnimTrack:
    enabled: bool = True
    keyframes: List[Keyframe] = field(default_factory=list)

    def remove_keyframe(self, time: float, tolerance: float = 5.0):
        self.keyframes = [kf for kf in self.keyframes if abs(kf.time - time) > tolerance]

@dataclass
class ClipData:
    """Represents a single piece of media on the timeline."""
    file_path: str
    start_time: int          # Where it starts on the timeline (in milliseconds)
    end_time: int            # Where it ends on the timeline (in milliseconds)
    trim_in: int = 0         # Milliseconds trimmed from the start of the raw file
    trim_out: int = 0        # Milliseconds trimmed from the end of the raw file
    clip_type: str = "video" # "video", "audio", or "text"
    clip_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    applied_effects: Dict = field(default_factory=dict)
    proxy_path: str = ""     
    animations: Dict[str, Any] = field(default_factory=dict) # Keyframing Support

    def __post_init__(self):
        """Deserializes dictionary data back into Keyframe/AnimTrack objects after loading."""
        restored_anims = {}
        for prop, track_data in self.animations.items():
            if isinstance(track_data, dict):
                kfs = []
                for kf_data in track_data.get("keyframes", []):
                    if isinstance(kf_data, dict):
                        ease_val = kf_data.get("easing", 0)
                        if isinstance(ease_val, int):
                            ease_val = Easing(ease_val)
                        elif isinstance(ease_val, str) and hasattr(Easing, ease_val.replace("Easing.", "")):
                            ease_val = Easing[ease_val.replace("Easing.", "")]
                            
                        kfs.append(Keyframe(
                            time=kf_data.get("time", 0.0),
                            value=kf_data.get("value", 0.0),
                            easing=ease_val
                        ))
                    else:
                        kfs.append(kf_data)
                restored_anims[prop] = AnimTrack(
                    enabled=track_data.get("enabled", True),
                    keyframes=kfs
                )
            else:
                restored_anims[prop] = track_data
        self.animations = restored_anims

    # --- Keyframing Logic ---
    def is_keyframing_enabled(self, prop: str) -> bool:
        return prop in self.animations and self.animations[prop].enabled

    def toggle_keyframing(self, prop: str, enabled: bool):
        if prop not in self.animations:
            self.animations[prop] = AnimTrack()
        self.animations[prop].enabled = enabled

    def set_keyframe(self, prop: str, time: float, value: float):
        if prop not in self.animations:
            self.animations[prop] = AnimTrack()
        
        track = self.animations[prop]
        # Update existing keyframe if clicked near the same time
        for kf in track.keyframes:
            if abs(kf.time - time) < 5.0:
                kf.value = value
                return
                
        # Otherwise add a new one and sort the timeline
        track.keyframes.append(Keyframe(time=time, value=value))
        track.keyframes.sort(key=lambda x: x.time)

    def get_keyframe_at_time(self, prop: str, time: float, tolerance: float = 5.0):
        if prop not in self.animations: return None
        for kf in self.animations[prop].keyframes:
            if abs(kf.time - time) <= tolerance:
                return kf
        return None

    def get_animated_value(self, prop: str, time: float, default_val):
        if not self.is_keyframing_enabled(prop):
            return default_val
            
        track = self.animations[prop]
        if not track.keyframes:
            return default_val
        
        # Extrapolate edges
        if time <= track.keyframes[0].time:
            return track.keyframes[0].value
        if time >= track.keyframes[-1].time:
            return track.keyframes[-1].value
            
        # Interpolate between closest keyframes
        for i in range(len(track.keyframes) - 1):
            k1 = track.keyframes[i]
            k2 = track.keyframes[i+1]
            if k1.time <= time <= k2.time:
                t = (time - k1.time) / (k2.time - k1.time)
                
                # Apply smooth easing math
                if k1.easing == Easing.EASE_IN:
                    t = t * t
                elif k1.easing == Easing.EASE_OUT:
                    t = t * (2 - t)
                elif k1.easing == Easing.EASE_IN_OUT:
                    t = t * t * (3 - 2 * t)
                elif k1.easing == Easing.CUBIC_IN:
                    t = t * t * t
                elif k1.easing == Easing.CUBIC_OUT:
                    t = 1 - math.pow(1 - t, 3)
                elif k1.easing == Easing.BOUNCE:
                    n1 = 7.5625
                    d1 = 2.75
                    if t < 1 / d1:
                        t = n1 * t * t
                    elif t < 2 / d1:
                        t -= 1.5 / d1
                        t = n1 * t * t + 0.75
                    elif t < 2.5 / d1:
                        t -= 2.25 / d1
                        t = n1 * t * t + 0.9375
                    else:
                        t -= 2.625 / d1
                        t = n1 * t * t + 0.984375
                elif k1.easing == Easing.ELASTIC:
                    c4 = (2 * math.pi) / 3
                    if t == 0:
                        t = 0
                    elif t == 1:
                        t = 1
                    else:
                        t = -math.pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * c4)
                    
                return k1.value + (k2.value - k1.value) * t
                
        return default_val

    def copy_attributes_from(self, other: 'ClipData'):
        """Supports the 'Paste Attributes' context menu feature."""
        self.applied_effects = copy.deepcopy(other.applied_effects)
        self.animations = copy.deepcopy(other.animations)

@dataclass
class TrackData:
    """Represents a horizontal row on the timeline holding multiple clips."""
    track_name: str
    track_type: str          # "video", "audio", "subtitle"
    clips: List[ClipData] = field(default_factory=list)
    track_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_muted: bool = False
    is_hidden: bool = False

@dataclass
class ProjectData:
    """The master object holding the entire state of the edit."""
    name: str = "Untitled Project"
    project_type: str = "standard"  
    resolution: tuple = (1920, 1080)
    fps: float = 30.0
    tracks: List[TrackData] = field(default_factory=list)
    media_bin: List[str] = field(default_factory=list) 
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))