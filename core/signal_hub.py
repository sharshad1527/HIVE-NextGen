#core/signal_hub.py
from PySide6.QtCore import QObject, Signal

class SignalHub(QObject):
    """
    The central nervous system of the NextGen UI.
    UI panels will listen to these signals instead of talking to each other directly.
    """
    project_loaded = Signal(object)
    project_saved = Signal(str) # FIXED: Added project saved signal
    project_resolution_changed = Signal(tuple) # FIXED: Added resolution swap signal
    
    playhead_moved = Signal(float)  # time in seconds
    playback_state_changed = Signal(bool)  # is_playing
    
    # Clip Selection & Modification
    clip_selected = Signal(str, str)  # FIXED: item_type, clip_id (fixes Player.py init crash)
    clip_deselected = Signal()        # FIXED: Added deselected state
    clip_updated = Signal(object)     # clip instance
    clip_transform_changed = Signal(str, str, object) # FIXED: clip_id, prop_name, value
    
    # Audio Background Processing
    waveform_ready = Signal(str, list) # FIXED: file_path, waveform_data
    
    # PHASE 1 & 3: Keyframe & Advanced Editing Signals
    force_refresh = Signal() # Forces ui/player.py to instantly repaint current frame
    keyframe_updated = Signal(object) # clip
    add_keyframe_requested = Signal() # Alt+K functionality
    
    # PHASE 2: Context Menus & Shortcuts
    clip_split_requested = Signal() 
    clip_cut_requested = Signal()
    clip_copy_requested = Signal()
    clip_paste_requested = Signal()
    clip_duplicate_requested = Signal()
    clip_delete_requested = Signal()
    paste_attributes_requested = Signal()
    
global_signals = SignalHub()