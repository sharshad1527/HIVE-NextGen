# ui/workspace.py
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QStackedWidget, QWidget)
from PySide6.QtCore import Qt, Signal

from core.signal_hub import global_signals
from core.logger import hive_logger as logger

# Absolute imports for components and mixins
from ui.workspace_components.mixins.media_bin import MediaBinMixin
from ui.workspace_components.mixins.effect_store import EffectStoreMixin
from ui.workspace_components.mixins.workspace_layout import WorkspaceLayoutMixin
from ui.workspace_components.mixins.workspace_sync import WorkspaceSyncMixin

class WorkspacePanel(MediaBinMixin, EffectStoreMixin, WorkspaceLayoutMixin, WorkspaceSyncMixin, QFrame):
    """
    Modularized WorkspacePanel using a Mixin-based architecture.
    Inheritance Order: Mixins first, QFrame last to ensure proper MRO.
    """
    add_item_to_timeline = Signal(dict)
    preview_requested = Signal(dict)
    media_load_started = Signal()
    media_load_finished = Signal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("Initializing WorkspacePanel (Modular Architecture)")
        
        self._init_base_state()
        self._init_styles()
        self._init_ui()
        self._connect_signals()
        
        logger.info("WorkspacePanel initialization complete")

    def _init_base_state(self):
        """Initializes the core state variables exactly as they appeared in the original monolithic class."""
        self.setObjectName("Panel")
        self.active_threads = set() 
        self.current_folder_path = None
        self.last_clicked_card = None
        self.all_media_cards = [] 
        self.sort_asc = True
        self._bulk_loading = False  # Suppresses per-card filter/sort during preload
        self._pending_batches = 0   # Track outstanding preload batches

    def _init_styles(self):
        """Preserves the original stylesheets and style variables."""
        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        self.input_style = """
            QLineEdit, QComboBox {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1; padding: 4px 8px; font-size: 11px;
            }
            QLineEdit:focus { border: 1px solid #e66b2c; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
        """
        
        self.btn_style_primary = """
            QPushButton {
                background-color: rgba(230, 107, 44, 0.15); color: #e66b2c; font-size: 11px; font-weight: bold;
                border: 1px solid rgba(230, 107, 44, 0.3); border-radius: 6px; padding: 6px;
            }
            QPushButton:hover { background-color: rgba(230, 107, 44, 0.3); color: #ffffff; }
        """
        
        self.btn_style_secondary = """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1; font-size: 11px;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; }
        """

    def _init_ui(self):
        """Constructs the UI components using methods from mixins."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tab_bar = QWidget()
        tab_bar.setStyleSheet("border-bottom: 1px solid rgba(255, 255, 255, 0.05);")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(15, 10, 15, 0)
        tab_layout.setSpacing(10)

        self.tabs = ["Workspace", "Media", "Captions", "Effects", "Transitions"]
        self.tab_buttons = []

        for i, tab_name in enumerate(self.tabs):
            btn = QPushButton(tab_name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent; border: none; color: #808080;
                    font-size: 10px; font-weight: bold; padding-bottom: 6px;
                    border-bottom: 2px solid transparent;
                }
                QPushButton:hover { color: #ffffff; }
                QPushButton:checked { color: #ffffff; border-bottom: 2px solid #e66b2c; }
            """)
            btn.clicked.connect(lambda checked=False, idx=i: self.switch_tab(idx))
            self.tab_buttons.append(btn)
            tab_layout.addWidget(btn)
        
        tab_layout.addStretch()
        layout.addWidget(tab_bar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Add tabs using mixin methods
        self.stack.addWidget(self._create_workspace_tab())
        self.stack.addWidget(self._create_media_tab())
        self.stack.addWidget(self._create_preset_tab("Captions", "mdi6.closed-caption-outline", ["Standard", "Pop-up", "Karaoke", "Typewriter", "Highlight"]))
        self.stack.addWidget(self._create_preset_tab("Effects", "mdi6.auto-fix", ["Blur", "Glow", "VHS", "Glitch", "Color Grade", "Vignette"]))
        self.stack.addWidget(self._create_preset_tab("Transitions", "mdi6.swap-horizontal", ["Cross Dissolve", "Dip to Black", "Wipe", "Zoom", "Slide", "Glitch"]))

        self.switch_tab(0)

    def _connect_signals(self):
        """Establishes global signal connections."""
        global_signals.project_loaded.connect(self._on_project_loaded)
