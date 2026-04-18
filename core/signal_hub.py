#core/signal_hub.py
from PySide6.QtCore import QObject, Signal

class SignalHub(QObject):
    """
    The central nervous system of the NextGen UI.
    UI panels will listen to these signals instead of talking to each other directly.
    """
    # Timeline Events
    clip_selected = Signal(str)         # Emits the clip_id (str)
    clip_deselected = Signal()          # Emits when background is clicked
    
    # Project Events
    project_loaded = Signal(object)     # Emits the ProjectData object
    project_saved = Signal(str)         # Emits the save path
    
    # Player Events
    playback_state_changed = Signal(bool) # True for playing, False for paused
    time_changed = Signal(int)          # Emits current time in milliseconds
    
    # Media Events
    waveform_ready = Signal(str, list)  # Emits file_path, peaks_array

# We create ONE global instance of this hub. 
# Everywhere else in the app, you will just: `from core.signal_hub import global_signals`
global_signals = SignalHub()