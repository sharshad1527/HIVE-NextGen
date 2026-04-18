#core/models.py

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import uuid

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
    proxy_path: str = ""     # NEW: Path to the 360p generated proxy file

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
    project_type: str = "standard"  # "standard" or "automated"
    resolution: tuple = (1920, 1080)
    fps: float = 30.0
    tracks: List[TrackData] = field(default_factory=list)
    media_bin: List[str] = field(default_factory=list) # Remembers imported media files!
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))