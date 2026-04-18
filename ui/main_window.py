# ui/main_window.py
import qtawesome as qta
import random
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QSplitter, QFrame, QGridLayout)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QImage, QPixmap

from ui.sidebar import Sidebar
from ui.workspace import WorkspacePanel
from ui.player import PlayerPanel
from ui.properties import PropertiesPanel
from ui.timeline.timeline_panel import TimelinePanel
from utils.shortcut_manager import ShortcutManager
from ui.settings_dialog import SettingsDialog
from core.project_manager import project_manager
from core.signal_hub import global_signals
from core.app_config import app_config

class CustomTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(44)
        self.parent_window = parent
        self.dragPos = QPoint()

        self.setStyleSheet("""
            QFrame#TitleBar {
                background-color: rgba(22, 22, 24, 0.85); 
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 12px;
            }
        """)

        layout = QGridLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(0)

        left_widget = QWidget()
        left_widget.setFixedWidth(140)
        left_layout = QHBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        self.lbl_save_icon = QLabel()
        self.lbl_save_text = QLabel("Saved")
        self.lbl_save_text.setStyleSheet("color: #808080; font-size: 11px; font-weight: bold;")
        
        left_layout.addWidget(self.lbl_save_icon)
        left_layout.addWidget(self.lbl_save_text)
        left_layout.addStretch()
        layout.addWidget(left_widget, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        
        self.set_saved_state(True)

        self.lbl_title = QLabel("H.I.V.E - Untitled Project")
        self.lbl_title.setObjectName("TitleBarBrand")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("color: #d1d1d1; font-size: 13px; font-weight: 500; letter-spacing: 1px;")
        self.lbl_title.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.lbl_title, 0, 1, Qt.AlignCenter)

        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        self.btn_min = QPushButton(qta.icon('mdi6.window-minimize', color='#808080'), "")
        self.btn_fullscreen = QPushButton(qta.icon('mdi6.window-maximize', color='#808080'), "")
        self.btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        
        for btn in [self.btn_min, self.btn_fullscreen, self.btn_close]:
            btn.setFixedSize(24, 24)
            btn.setObjectName("TitleBarBtn")
            btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; border-radius: 4px; }
                QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
            """)
            
        self.btn_close.setObjectName("TitleBarCloseBtn")
        self.btn_close.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #e81123; }
        """)

        self.btn_min.clicked.connect(self.parent_window.showMinimized)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        self.btn_close.clicked.connect(self.parent_window.close)

        right_layout.addWidget(self.btn_min)
        right_layout.addWidget(self.btn_fullscreen)
        right_layout.addWidget(self.btn_close)
        
        layout.addWidget(right_widget, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        
        global_signals.project_loaded.connect(self.update_title)

        if project_manager.current_project:
            self.update_title(project_manager.current_project)

    def set_saved_state(self, is_saved):
        if is_saved:
            self.lbl_save_icon.setPixmap(qta.icon('mdi6.cloud-check', color='#4CAF50').pixmap(16, 16)) 
            self.lbl_save_text.setText("Saved")
            self.lbl_save_text.setStyleSheet("color: #808080; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_save_icon.setPixmap(qta.icon('mdi6.circle-edit-outline', color='#e66b2c').pixmap(16, 16)) 
            self.lbl_save_text.setText("Saving...")
            self.lbl_save_text.setStyleSheet("color: #e66b2c; font-size: 11px; font-weight: bold;")
        
    def update_title(self, project_data):
        if project_data:
            self.lbl_title.setText(f"H.I.V.E - {project_data.name}")

    def toggle_fullscreen(self):
        if self.parent_window.isFullScreen():
            self.parent_window.showMaximized()
            self.btn_fullscreen.setIcon(qta.icon('mdi6.window-maximize', color='#808080'))
        else:
            self.parent_window.showFullScreen()
            self.btn_fullscreen.setIcon(qta.icon('mdi6.window-restore', color='#808080'))

    def toggle_maximize(self):
        if self.parent_window.isFullScreen():
            self.parent_window.showNormal()
            self.btn_fullscreen.setIcon(qta.icon('mdi6.window-maximize', color='#808080'))
            
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.parent_window.isMaximized() and not self.parent_window.isFullScreen():
            self.parent_window.move(self.parent_window.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximize()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
        self.resize(1280, 720)
        self._generate_premium_background_texture()
        
        self.setup_ui()
        self.setup_shortcuts()
        self.setup_autosave()
        
        # FIX: Ensure MainWindow catches the project load to fill the Media Bin
        global_signals.project_loaded.connect(self.on_project_loaded)
        if project_manager.current_project:
            QTimer.singleShot(0, lambda: self.on_project_loaded(project_manager.current_project))
            
        self.showMaximized()

    def _generate_premium_background_texture(self):
        size = 128
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        for y in range(size):
            for x in range(size):
                if random.random() > 0.25:
                    intensity = random.randint(0, 18)
                    if (x + y) % 4 == 0: intensity += 8
                    if (x - y) % 4 == 0: intensity -= 4
                    intensity = max(0, min(255, intensity))
                    image.setPixelColor(x, y, QColor(0, 0, 0, intensity + 15))
                else:
                    if random.random() > 0.8:
                        image.setPixelColor(x, y, QColor(255, 255, 255, random.randint(2, 6)))
        self.bg_texture = QPixmap.fromImage(image)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        center = self.rect().center()
        gradient = QRadialGradient(center, self.width() / 1.1)
        gradient.setColorAt(0.0, QColor(22, 22, 25))
        gradient.setColorAt(0.6, QColor(8, 8, 10))
        gradient.setColorAt(1.0, QColor(0, 0, 0))
        
        painter.fillRect(self.rect(), gradient)
        painter.drawTiledPixmap(self.rect(), self.bg_texture)

    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(12)

        self.title_bar = CustomTitleBar(self)
        editor_layout.addWidget(self.title_bar)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.top_panels_splitter = QSplitter(Qt.Horizontal)
        
        self.panel_workspace = WorkspacePanel()
        self.panel_player = PlayerPanel()
        self.panel_properties = PropertiesPanel()

        self.top_panels_splitter.addWidget(self.panel_workspace)
        self.top_panels_splitter.addWidget(self.panel_player)
        self.top_panels_splitter.addWidget(self.panel_properties)
        self.top_panels_splitter.setSizes([350, 600, 250])

        self.panel_timeline = TimelinePanel()

        self.panel_timeline.tracks_canvas.item_clicked.connect(self.panel_properties.show_properties)
        self.panel_properties.property_changed.connect(self.panel_timeline.tracks_canvas.update_item_property)

        self.panel_timeline.tracks_canvas.v1_duration_changed.connect(self.panel_player.update_duration)
        self.panel_timeline.tracks_canvas.playhead_changed.connect(self.panel_player.update_playhead)
        self.panel_player.playhead_seek_requested.connect(self.panel_timeline.tracks_canvas.set_playhead)

        self.panel_workspace.add_item_to_timeline.connect(self.panel_timeline.tracks_canvas.add_item_directly)
        self.panel_workspace.preview_requested.connect(self.panel_player.load_preview)

        initial_duration = self.panel_timeline.tracks_canvas.get_v1_duration()
        self.panel_player.update_duration(initial_duration)
        self.panel_player.update_playhead(self.panel_timeline.tracks_canvas.logical_playhead)

        self.main_splitter.addWidget(self.top_panels_splitter)
        self.main_splitter.addWidget(self.panel_timeline)
        self.main_splitter.setSizes([400, 300])

        editor_layout.addWidget(self.main_splitter)
        main_layout.addWidget(editor_widget)

    def setup_autosave(self):
        self.is_dirty = False
        
        # We keep a background timer using user settings
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save_project)
        
        # Pull interval from settings (convert minutes to milliseconds)
        interval_mins = app_config.get_setting("auto_save_interval", 5)
        self.auto_save_timer.start(interval_mins * 60 * 1000)
        
        # FIX: Every edit made tries to instantly save the project
        self.panel_timeline.tracks_canvas.state_changed.connect(self.mark_unsaved)

    def mark_unsaved(self):
        """Called whenever the timeline changes. Respects auto-save toggle setting."""
        if not self.is_dirty:
            self.is_dirty = True
            self.title_bar.set_saved_state(False)
            
        # Trigger an immediate save if enabled
        if app_config.get_setting("auto_save_enabled", True):
            self.save_current_project()

    def auto_save_project(self):
        """Background saving loop. Respects auto-save toggle setting."""
        if self.is_dirty and app_config.get_setting("auto_save_enabled", True):
            print("Auto-Saving in background...")
            self.save_current_project()

    def setup_shortcuts(self):
        self.shortcut_manager = ShortcutManager(self)
        self.sidebar.btn_shortcuts.clicked.connect(self.shortcut_manager.show_editor)
        self.shortcut_manager.sig_save_project.connect(self.save_current_project)
        self.shortcut_manager.sig_play_pause.connect(self.panel_player.toggle_play)
        self.shortcut_manager.sig_step_forward.connect(self.panel_player.step_forward)
        self.shortcut_manager.sig_step_backward.connect(self.panel_player.step_backward)
        self.shortcut_manager.sig_tool_pointer.connect(self.panel_timeline.btn_pointer.click)
        self.shortcut_manager.sig_tool_blade.connect(self.panel_timeline.btn_blade.click)
        self.shortcut_manager.sig_toggle_snap.connect(self.panel_timeline.btn_magnet.click)
        self.shortcut_manager.sig_toggle_gravity.connect(self.panel_timeline.btn_gravity.click)
        self.shortcut_manager.sig_delete_item.connect(self.panel_timeline.btn_trash.click)
        self.shortcut_manager.sig_undo.connect(self.panel_timeline.btn_undo.click)
        self.shortcut_manager.sig_redo.connect(self.panel_timeline.btn_redo.click)
        self.shortcut_manager.sig_split_playhead.connect(self.panel_timeline.btn_split.click)
        self.shortcut_manager.sig_trim_left.connect(self.panel_timeline.btn_trim_left.click)
        self.shortcut_manager.sig_trim_right.connect(self.panel_timeline.btn_trim_right.click)
        self.shortcut_manager.sig_freeze_frame.connect(self.panel_timeline.btn_freeze.click)
        self.shortcut_manager.sig_reverse.connect(self.panel_timeline.btn_reverse.click)
        self.shortcut_manager.sig_mirror.connect(self.panel_timeline.btn_mirror.click)
        self.shortcut_manager.sig_rotate.connect(self.panel_timeline.btn_rotate.click)
        self.shortcut_manager.sig_crop.connect(self.panel_timeline.btn_crop.click)
        self.shortcut_manager.sig_zoom_in.connect(self.panel_timeline.btn_zoom_in.click)
        self.shortcut_manager.sig_zoom_out.connect(self.panel_timeline.btn_zoom_out.click)
        self.sidebar.btn_settings.clicked.connect(self.open_settings)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
        self.sidebar.clear_selection() # Reset sidebar styling state
        
        # Sync the interval live just in case it was changed
        interval_mins = app_config.get_setting("auto_save_interval", 5)
        self.auto_save_timer.setInterval(interval_mins * 60 * 1000)
        
    def save_current_project(self):
        """Packs Timeline data, saves to .hive file, and resets UI indicators."""
        self.panel_timeline.tracks_canvas.sync_to_project()
        
        duration_str = self.panel_timeline.tracks_canvas.get_formatted_duration()
        
        if project_manager.save_project(duration_str=duration_str):
            self.is_dirty = False
            self.title_bar.set_saved_state(True)
            
    def on_project_loaded(self, project_data):
        print(f"MAIN WINDOW: Loading Workspace Media Bin...")
        # Reload Media Bin files instantly upon startup
        if hasattr(project_data, 'media_bin') and project_data.media_bin:
            self.panel_workspace.load_media_bin_from_paths(project_data.media_bin)
        else:
            self.panel_workspace.clear_media_bin()
            
    def closeEvent(self, event):
        """Guarantees the project is saved before the window is destroyed."""
        print("Safeguard: Executing final save before closing...")
        self.save_current_project()
        event.accept()