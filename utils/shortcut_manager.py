# utils/shortcut_manager.py
import qtawesome as qta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QScrollArea, QWidget, QGridLayout, 
                               QKeySequenceEdit, QFrame)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt, Signal, QObject

from core.signal_hub import global_signals

# Default professional shortcuts
DEFAULT_SHORTCUTS = {
    "Save Project": {"seq": "Ctrl+S", "signal": "sig_save_project"},
    "Play / Pause": {"seq": "Space", "signal": "sig_play_pause"},
    "Pointer Tool": {"seq": "V", "signal": "sig_tool_pointer"},
    "Blade Tool": {"seq": "C", "signal": "sig_tool_blade"},
    "Toggle Snapping": {"seq": "S", "signal": "sig_toggle_snap"},
    "Toggle Gravity": {"seq": "G", "signal": "sig_toggle_gravity"},
    "Delete Item": {"seq": "Del", "signal": "sig_delete_item"},
    "Copy Item": {"seq": "Ctrl+C", "signal": "sig_copy_item"},
    "Paste Item": {"seq": "Ctrl+V", "signal": "sig_paste_item"},
    "Cut Item": {"seq": "Ctrl+X", "signal": "sig_cut_item"},
    "Duplicate Item": {"seq": "Ctrl+D", "signal": "sig_duplicate_item"},
    "Next Frame": {"seq": "Right", "signal": "sig_step_forward"},
    "Previous Frame": {"seq": "Left", "signal": "sig_step_backward"},
    "Zoom In": {"seq": "=", "signal": "sig_zoom_in"},
    "Zoom Out": {"seq": "-", "signal": "sig_zoom_out"},
    "Undo": {"seq": "Ctrl+Z", "signal": "sig_undo"},
    "Redo": {"seq": "Ctrl+Shift+Z", "signal": "sig_redo"},
    "Split at Playhead": {"seq": "Ctrl+K", "signal": "sig_split_playhead"},
    "Trim Left": {"seq": "Q", "signal": "sig_trim_left"},
    "Trim Right": {"seq": "W", "signal": "sig_trim_right"},
    "Freeze Frame": {"seq": "Shift+F", "signal": "sig_freeze_frame"},
    "Reverse": {"seq": "Ctrl+R", "signal": "sig_reverse"},
    "Mirror": {"seq": "Alt+M", "signal": "sig_mirror"},
    "Rotate": {"seq": "Alt+R", "signal": "sig_rotate"},
    "Crop": {"seq": "Alt+C", "signal": "sig_crop"},
    "Add Keyframe": {"seq": "Alt+K", "signal": "sig_add_keyframe"}
}

class ShortcutEditorDialog(QDialog):
    """Sleek UI Dialog to edit shortcuts."""
    def __init__(self, current_shortcuts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setFixedSize(450, 550)
        self.current_shortcuts = current_shortcuts.copy()
        self.edits = {}

        self.setStyleSheet("""
            QDialog {
                background-color: #111111;
                border: 1px solid #262626;
                border-radius: 10px;
            }
            QLabel { color: #d1d1d1; font-size: 12px; font-weight: bold; }
            QKeySequenceEdit {
                background-color: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #e66b2c;
                padding: 6px; font-family: monospace; font-size: 12px;
            }
            QKeySequenceEdit:focus { border: 1px solid #e66b2c; }
            QPushButton {
                background-color: rgba(230, 107, 44, 0.15); color: #e66b2c; font-size: 11px; font-weight: bold;
                border: 1px solid rgba(230, 107, 44, 0.3); border-radius: 6px; padding: 8px 16px;
            }
            QPushButton:hover { background-color: rgba(230, 107, 44, 0.3); color: #ffffff; }
            QPushButton#CancelBtn {
                background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QPushButton#CancelBtn:hover { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Keyboard Shortcuts")
        header.setStyleSheet("font-size: 16px; color: #ffffff; margin-bottom: 10px;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setSpacing(15)
        
        row = 0
        for action, data in self.current_shortcuts.items():
            lbl = QLabel(action)
            seq_edit = QKeySequenceEdit(QKeySequence(data["seq"]))
            self.edits[action] = seq_edit
            
            grid.addWidget(lbl, row, 0)
            grid.addWidget(seq_edit, row, 1)
            row += 1
            
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("CancelBtn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("Save Shortcuts")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self.save_and_close)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def save_and_close(self):
        for action, edit in self.edits.items():
            self.current_shortcuts[action]["seq"] = edit.keySequence().toString()
        self.accept()


class ShortcutManager(QObject):
    """Central Controller for Global Application Shortcuts"""
    sig_save_project = Signal()
    sig_play_pause = Signal()
    sig_tool_pointer = Signal()
    sig_tool_blade = Signal()
    sig_toggle_snap = Signal()
    sig_toggle_gravity = Signal()
    sig_delete_item = Signal()
    sig_copy_item = Signal()
    sig_paste_item = Signal()
    sig_cut_item = Signal()
    sig_duplicate_item = Signal()
    sig_step_forward = Signal()
    sig_step_backward = Signal()
    sig_zoom_in = Signal()
    sig_zoom_out = Signal()
    sig_undo = Signal()
    sig_redo = Signal()
    sig_split_playhead = Signal()
    sig_trim_left = Signal()
    sig_trim_right = Signal()
    sig_freeze_frame = Signal()
    sig_reverse = Signal()
    sig_mirror = Signal()
    sig_rotate = Signal()
    sig_crop = Signal()
    sig_add_keyframe = Signal()

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.shortcuts_config = DEFAULT_SHORTCUTS.copy()
        self._active_qshortcuts = []
        
        self.apply_shortcuts()
        self._bind_to_global_signals()

    def _bind_to_global_signals(self):
        """Automatically wire up edit actions to the global signal hub"""
        if hasattr(global_signals, 'clip_copy_requested'):
            self.sig_copy_item.connect(global_signals.clip_copy_requested.emit)
        if hasattr(global_signals, 'clip_paste_requested'):
            self.sig_paste_item.connect(global_signals.clip_paste_requested.emit)
        if hasattr(global_signals, 'clip_cut_requested'):
            self.sig_cut_item.connect(global_signals.clip_cut_requested.emit)
        if hasattr(global_signals, 'clip_duplicate_requested'):
            self.sig_duplicate_item.connect(global_signals.clip_duplicate_requested.emit)
        if hasattr(global_signals, 'clip_delete_requested'):
            self.sig_delete_item.connect(global_signals.clip_delete_requested.emit)
        if hasattr(global_signals, 'clip_split_requested'):
            self.sig_split_playhead.connect(global_signals.clip_split_requested.emit)
        if hasattr(global_signals, 'add_keyframe_requested'):
            self.sig_add_keyframe.connect(global_signals.add_keyframe_requested.emit)

    def apply_shortcuts(self):
        for sc in self._active_qshortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._active_qshortcuts.clear()

        for action, data in self.shortcuts_config.items():
            seq = data["seq"]
            sig_name = data["signal"]
            
            if seq:
                shortcut = QShortcut(QKeySequence(seq), self.parent_window)
                shortcut.setContext(Qt.ApplicationShortcut)
                signal_obj = getattr(self, sig_name)
                shortcut.activated.connect(signal_obj.emit)
                self._active_qshortcuts.append(shortcut)
                
        # Hardcode Backspace fallback for deletion
        bs_shortcut = QShortcut(QKeySequence("Backspace"), self.parent_window)
        bs_shortcut.setContext(Qt.ApplicationShortcut)
        bs_shortcut.activated.connect(self.sig_delete_item.emit)
        self._active_qshortcuts.append(bs_shortcut)

    def show_editor(self):
        dialog = ShortcutEditorDialog(self.shortcuts_config, self.parent_window)
        if dialog.exec() == QDialog.Accepted:
            self.shortcuts_config = dialog.current_shortcuts
            self.apply_shortcuts()