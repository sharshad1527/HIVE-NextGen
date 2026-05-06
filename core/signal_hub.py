#core/signal_hub.py
from PySide6.QtCore import QObject, Signal

class SignalHub(QObject):
    """
    The central nervous system of the NextGen UI.
    UI panels will listen to these signals instead of talking to each other directly.
    """
    project_loaded = Signal(object)
    project_saved = Signal(str) # Added project saved signal
    project_renamed = Signal(str) # Added project renamed signal
    project_resolution_changed = Signal(tuple) # Added resolution swap signal
    
    playhead_moved = Signal(float)  # time in seconds
    playback_state_changed = Signal(bool)  # is_playing
    
    # Clip Selection & Modification
    clip_selected = Signal(str, str)  # item_type, clip_id (fixes Player.py init crash)
    clip_deselected = Signal()        # Added deselected state
    clip_updated = Signal(object)     # clip instance
    clip_transform_changed = Signal(str, str, object) # clip_id, prop_name, value

    # Clips Import & Delete
    clip_added = Signal(str)      # Sends the new clip_id
    clip_removed = Signal(str)    # Sends the deleted clip_id
    
    # Audio Background Processing
    waveform_ready = Signal(str, list) # file_path, waveform_data
    
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

    # Emits the new memory limit in MB
    memory_limit_changed = Signal(int)

    timeline_updated = Signal()
    auto_scroll_requested = Signal()

    # Settings & UI Evolution
    settings_changed = Signal(str, object) # key, value
    theme_changed = Signal(str) # theme_name
    
    # Logging
    log_emitted = Signal(str, str) # log_entry, levelname
    
global_signals = SignalHub()