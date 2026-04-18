# ui/workspace.py
import qtawesome as qta
import json
import os
import shutil
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QStackedWidget, QWidget, QScrollArea, 
                               QGridLayout, QLineEdit, QComboBox, QFileDialog, QProgressBar, QDialog, QCheckBox)
from PySide6.QtCore import Qt, QMimeData, Signal, QThread
from PySide6.QtGui import QDrag, QPixmap

from core.media_manager import media_manager
from core.project_manager import project_manager
from core.app_config import app_config
from core.signal_hub import global_signals

class MediaLoaderThread(QThread):
    """Background Thread: Processes heavy files (OpenCV Video extraction) without freezing the UI!"""
    item_processed = Signal(dict)
    
    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        
    def run(self):
        for path in self.paths:
            info = media_manager.process_file(path)
            if info:
                self.item_processed.emit(info)

class DraggableCard(QFrame):
    add_requested = Signal(dict)
    preview_requested = Signal(dict)

    def __init__(self, title, icon_name, item_type, subtype="", file_path="", thumbnail=None):
        super().__init__()
        self.title = title
        self.item_type = item_type
        self.subtype = subtype
        self.file_path = file_path
        self.thumbnail_path = thumbnail
        self.proxy_path = "" # Will be filled if proxy generation succeeds
        
        self.setFixedSize(145, 120) 
        self.setCursor(Qt.PointingHandCursor)
        
        self.setStyleSheet("""
            QFrame { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; }
            QFrame:hover { border: 1px solid rgba(230, 107, 44, 0.5); }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)
        
        # 1. Image Container (Allows layering progress bar over it)
        self.img_container = QWidget()
        self.img_container.setFixedSize(135, 75)
        img_layout = QVBoxLayout(self.img_container)
        img_layout.setContentsMargins(0,0,0,0)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(135, 75)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet("background-color: #0a0a0a; border-radius: 4px; border: none;")

        if thumbnail and os.path.exists(thumbnail):
            pixmap = QPixmap(thumbnail)
            scaled_pixmap = pixmap.scaled(135, 75, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb_lbl.setPixmap(scaled_pixmap)
        else:
            self.thumb_lbl.setPixmap(qta.icon(icon_name, color='#a0a0a0').pixmap(24, 24))
            
        # 1a. Progress Bar for Proxy Generation (Hidden by default)
        self.progress_bar = QProgressBar(self.thumb_lbl)
        self.progress_bar.setGeometry(10, 60, 115, 6) # Small sleek bar at bottom of thumbnail
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: rgba(0,0,0,0.5); border-radius: 3px; }
            QProgressBar::chunk { background-color: #e66b2c; border-radius: 3px; }
        """)
        self.progress_bar.hide()
            
        img_layout.addWidget(self.thumb_lbl)
        layout.addWidget(self.img_container)

        # 2. Text Label below the image
        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        metrics = self.title_lbl.fontMetrics()
        elided_title = metrics.elidedText(title, Qt.ElideRight, 130)
        self.title_lbl.setText(elided_title)
        self.title_lbl.setStyleSheet("color: #d1d1d1; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        
        layout.addWidget(self.title_lbl)
        
        # 3. The floating '+' Add Button
        self.btn_add = QPushButton(qta.icon('mdi6.plus', color="#ffffff"), "", self)
        self.btn_add.setGeometry(115, 10, 22, 22)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.setStyleSheet("""
            QPushButton { background-color: rgba(230, 107, 44, 0.8); border-radius: 11px; border: 1px solid #ffffff; }
            QPushButton:hover { background-color: rgba(230, 107, 44, 1.0); }
        """)
        self.btn_add.clicked.connect(self._on_add_clicked)

        self.drag_start_pos = None

    def update_proxy_progress(self, percentage):
        if percentage < 100:
            self.progress_bar.show()
            self.progress_bar.setValue(percentage)
        else:
            self.progress_bar.hide()

    def set_proxy_path(self, path):
        self.proxy_path = path

    def get_data(self):
        return {
            "title": self.title, 
            "type": self.item_type, 
            "subtype": self.subtype,
            "file_path": self.file_path,
            "proxy_path": self.proxy_path,
            "thumbnail": self.thumbnail_path
        }

    def _on_add_clicked(self):
        self.add_requested.emit(self.get_data())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not self.drag_start_pos:
            return
        if (event.position().toPoint() - self.drag_start_pos).manhattanLength() < 5:
            return
            
        drag = QDrag(self)
        mime = QMimeData()
        data = json.dumps(self.get_data())
        mime.setData("application/x-have-item", data.encode('utf-8'))
        drag.setMimeData(mime)
        
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())
        
        drag.exec(Qt.CopyAction)
        self.drag_start_pos = None

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drag_start_pos:
            self.preview_requested.emit(self.get_data())
        self.drag_start_pos = None

class ProjectSettingsDialog(QDialog):
    """A sleek dialog specifically for editing the active project's settings"""
    def __init__(self, current_res, current_fps, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Project Settings")
        self.setFixedSize(400, 280)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #111111;
                border: 1px solid #262626;
                border-radius: 10px;
            }
            QLabel { color: #d1d1d1; font-weight: bold; font-size: 12px; }
            QComboBox {
                background-color: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; color: #d1d1d1; padding: 6px 10px; font-size: 12px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
            QCheckBox { color: #d1d1d1; font-weight: bold; font-size: 12px;}
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); }
            QCheckBox::indicator:checked { background-color: #e66b2c; border: 1px solid #e66b2c; image: url(none); }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; }
            QPushButton#PrimaryBtn {
                background-color: rgba(230, 107, 44, 0.8); color: #ffffff; border: none;
            }
            QPushButton#PrimaryBtn:hover { background-color: #e66b2c; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)

        # Custom Title Bar
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #151515; border-bottom: 1px solid #262626; border-top-left-radius: 10px; border-top-right-radius: 10px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        lbl_title = QLabel("Current Project Settings")
        lbl_title.setStyleSheet("border: none;")
        
        btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #e81123; }")
        btn_close.clicked.connect(self.reject)
        
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()
        title_layout.addWidget(btn_close)
        layout.addWidget(title_bar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Resolution Dropdown
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Resolution:"))
        self.cb_res = QComboBox()
        self.res_options = {
            "3840x2160 (4K)": (3840, 2160),
            "1920x1080 (HD)": (1920, 1080),
            "1080x1920 (9:16 Vertical)": (1080, 1920),
            "1080x1080 (Square)": (1080, 1080)
        }
        self.cb_res.addItems(list(self.res_options.keys()))
        
        for k, v in self.res_options.items():
            if v == current_res:
                self.cb_res.setCurrentText(k)
                break
        self.cb_res.setFixedWidth(200)
        res_layout.addStretch()
        res_layout.addWidget(self.cb_res)
        content_layout.addLayout(res_layout)

        # FPS Dropdown
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("Frame Rate:"))
        self.cb_fps = QComboBox()
        fps_options = ["23.976", "24", "25", "29.97", "30", "50", "60"]
        self.cb_fps.addItems(fps_options)
        
        current_fps_str = str(current_fps).rstrip('0').rstrip('.') if current_fps % 1 == 0 else str(current_fps)
        if current_fps_str in fps_options:
            self.cb_fps.setCurrentText(current_fps_str)
        self.cb_fps.setFixedWidth(200)
        fps_layout.addStretch()
        fps_layout.addWidget(self.cb_fps)
        content_layout.addLayout(fps_layout)

        # File Handling Toggle
        self.chk_copy_media = QCheckBox("Copy imported media to project directory")
        self.chk_copy_media.setChecked(app_config.get_setting("copy_media_to_project", False))
        content_layout.addWidget(self.chk_copy_media)

        content_layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("Save Settings")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        content_layout.addLayout(btn_layout)

        layout.addWidget(content)

    def get_resolution(self):
        return self.res_options[self.cb_res.currentText()]

    def get_fps(self):
        return float(self.cb_fps.currentText())

class WorkspacePanel(QFrame):
    add_item_to_timeline = Signal(dict)
    preview_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        
        self.media_row = 0
        self.media_col = 0
        self.active_threads = set() 
        self.media_cards = {} # Cache to map file paths to DraggableCard UI widgets
        
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
            btn.clicked.connect(lambda checked, index=i: self.switch_tab(index))
            self.tab_buttons.append(btn)
            tab_layout.addWidget(btn)
        
        tab_layout.addStretch()
        layout.addWidget(tab_bar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.stack.addWidget(self._create_workspace_tab())
        self.stack.addWidget(self._create_media_tab())
        self.stack.addWidget(self._create_preset_tab("Captions", "mdi6.closed-caption-outline", ["Standard", "Pop-up", "Karaoke", "Typewriter", "Highlight"]))
        self.stack.addWidget(self._create_preset_tab("Effects", "mdi6.auto-fix", ["Blur", "Glow", "VHS", "Glitch", "Color Grade", "Vignette"]))
        self.stack.addWidget(self._create_preset_tab("Transitions", "mdi6.swap-horizontal", ["Cross Dissolve", "Dip to Black", "Wipe", "Zoom", "Slide", "Glitch"]))

        self.switch_tab(0)
        
        # Listen for when a project loads so we can update the UI labels
        global_signals.project_loaded.connect(self._on_project_loaded)

    def switch_tab(self, index):
        for i, btn in enumerate(self.tab_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def _create_grid_scroll(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #555; }
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content)
        return scroll, grid

    def _create_workspace_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        lbl_auto = QLabel("Project Automation")
        lbl_auto.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_auto)

        btn_whisper = self._create_action_button("mdi6.microphone-outline", "#e66b2c", "Sync with Whisper AI", "Auto-align script to audio")
        btn_captions = self._create_action_button("mdi6.closed-caption-outline", "#4299e1", "Generate Captions", "Create blocks from script")
        
        layout.addWidget(btn_whisper)
        layout.addWidget(btn_captions)

        layout.addSpacing(10)
        lbl_settings = QLabel("Project Settings")
        lbl_settings.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_settings)

        settings_box = QFrame()
        settings_box.setStyleSheet("background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px;")
        box_layout = QVBoxLayout(settings_box)
        
        def add_setting_row(label, value):
            row = QHBoxLayout()
            lbl1 = QLabel(label)
            lbl1.setStyleSheet("color: #808080; font-size: 11px;")
            lbl2 = QLabel(value)
            lbl2.setStyleSheet("color: #d1d1d1; font-size: 11px; font-family: monospace;")
            row.addWidget(lbl1)
            row.addStretch()
            row.addWidget(lbl2)
            box_layout.addLayout(row)
            return lbl2

        self.lbl_res_value = add_setting_row("Resolution", "1920x1080 (HD)")
        self.lbl_fps_value = add_setting_row("Framerate", "30 fps")
        
        btn_edit_settings = QPushButton(qta.icon('mdi6.cog-outline', color='#e66b2c'), " Edit Settings")
        btn_edit_settings.setStyleSheet(self.btn_style_primary)
        btn_edit_settings.setCursor(Qt.PointingHandCursor)
        btn_edit_settings.clicked.connect(self._open_project_settings)
        box_layout.addWidget(btn_edit_settings)

        layout.addWidget(settings_box)
        return widget

    def _on_project_loaded(self, project_data):
        """Updates the labels in the Workspace tab based on the active project."""
        self._update_settings_labels(project_data)

    def _open_project_settings(self):
        """Opens the dialog to edit the active project's settings."""
        if not project_manager.current_project:
            return
            
        was_copy_enabled = app_config.get_setting("copy_media_to_project", False)
            
        dialog = ProjectSettingsDialog(
            project_manager.current_project.resolution, 
            project_manager.current_project.fps, 
            self
        )
        
        if dialog.exec():
            now_copy_enabled = dialog.chk_copy_media.isChecked()
            
            # Apply Settings back to App Config
            app_config.set_setting("copy_media_to_project", now_copy_enabled)
            
            # Update the project object
            project_manager.current_project.resolution = dialog.get_resolution()
            project_manager.current_project.fps = dialog.get_fps()
            
            # Immediately save and update the UI
            self._update_settings_labels(project_manager.current_project)
            project_manager.save_project()
            
            # Retroactively copy media into project folder if the user just enabled the option mid-edit
            if now_copy_enabled and not was_copy_enabled:
                self._retroactively_copy_media()

    def _retroactively_copy_media(self):
        """Copies all existing media in the bin to the project folder if the setting was turned on late."""
        proj_dir = os.path.dirname(project_manager.project_path) if project_manager.project_path else None
        if not proj_dir: return

        media_dir = os.path.join(proj_dir, "media")
        os.makedirs(media_dir, exist_ok=True)

        updated_paths = []
        path_mapping = {}
        changed = False

        for path in project_manager.current_project.media_bin:
            filename = os.path.basename(path)
            dest_path = os.path.join(media_dir, filename).replace('\\', '/')

            old_abs = os.path.abspath(path)
            dest_abs = os.path.abspath(dest_path)

            if not os.path.exists(dest_path) or old_abs != dest_abs:
                try:
                    shutil.copy2(path, dest_path)
                    updated_paths.append(dest_path)
                    path_mapping[old_abs] = dest_path
                    changed = True
                except Exception as e:
                    print(f"Failed to retroactively copy media file {path}: {e}")
                    updated_paths.append(path)
            else:
                updated_paths.append(path)

        if changed:
            # 1. Update the overall media bin in project data
            project_manager.current_project.media_bin = updated_paths
            
            # 2. Update file_path references on clips already placed in the timeline
            for track in project_manager.current_project.tracks:
                for clip in track.clips:
                    if clip.file_path:
                        c_abs = os.path.abspath(clip.file_path)
                        if c_abs in path_mapping:
                            clip.file_path = path_mapping[c_abs]

            project_manager.save_project()
            
            # 3. Reload media UI safely with new paths
            self.load_media_bin_from_paths(updated_paths)
            
            # 4. Trigger UI reload of the timeline to ensure safe sync
            global_signals.project_loaded.emit(project_manager.current_project)

    def _update_settings_labels(self, project):
        if not project:
            return
            
        res = project.resolution
        fps = project.fps
        
        # Format resolution for UI
        res_str = f"{res[0]}x{res[1]}"
        if res == (3840, 2160): res_str += " (4K)"
        elif res == (1920, 1080): res_str += " (HD)"
        elif res == (1080, 1920): res_str += " (9:16 Vertical)"
        elif res == (1080, 1080): res_str += " (Square)"
            
        self.lbl_res_value.setText(res_str)
        
        # Clean formatting for floats (e.g. 30.0 -> 30, 23.976 -> 23.976)
        fps_str = str(fps).rstrip('0').rstrip('.') if fps % 1 == 0 else str(fps)
        self.lbl_fps_value.setText(f"{fps_str} fps")

    def _create_action_button(self, icon_name, icon_color, title, subtitle):
        btn = QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; text-align: left; padding: 10px; }
            QPushButton:hover { background-color: rgba(34, 34, 34, 0.8); border: 1px solid rgba(230, 107, 44, 0.5); }
        """)
        layout = QHBoxLayout(btn)
        layout.setContentsMargins(5, 5, 5, 5)
        
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(18, 18))
        layout.addWidget(icon_lbl)
        
        text_layout = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold; background: transparent; border: none;")
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #808080; font-size: 10px; background: transparent; border: none;")
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(sub_lbl)
        
        layout.addLayout(text_layout)
        layout.addStretch()
        return btn

    def _create_media_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        import_layout = QHBoxLayout()
        btn_import_files = QPushButton(qta.icon('mdi6.file-import-outline', color='#e66b2c'), " Import Files")
        btn_import_files.setStyleSheet(self.btn_style_primary)
        btn_import_files.setCursor(Qt.PointingHandCursor)
        btn_import_files.clicked.connect(self._import_media_files)
        
        btn_import_folder = QPushButton(qta.icon('mdi6.folder-plus-outline', color='#d1d1d1'), " Folder")
        btn_import_folder.setStyleSheet(self.btn_style_secondary)
        btn_import_folder.setCursor(Qt.PointingHandCursor)
        btn_import_folder.clicked.connect(self._import_folder)
        
        import_layout.addWidget(btn_import_files, stretch=2)
        import_layout.addWidget(btn_import_folder, stretch=1)
        layout.addLayout(import_layout)

        search = QLineEdit()
        search.setPlaceholderText("Search media...")
        search.setStyleSheet(self.input_style)
        layout.addWidget(search)

        self.media_scroll, self.media_grid = self._create_grid_scroll()
        layout.addWidget(self.media_scroll)
        return widget

    def clear_media_bin(self):
        while self.media_grid.count():
            item = self.media_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.media_row = 0
        self.media_col = 0
        self.media_cards.clear()

    def load_media_bin_from_paths(self, paths):
        self.clear_media_bin()
        self._process_media_files_async(paths)

    def _import_media_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Media Files", "", 
            "Media Files (*.mp4 *.mov *.avi *.mkv *.webm *.wav *.mp3 *.aac *.png *.jpg *.jpeg *.webp)"
        )
        if file_paths and project_manager.current_project:
            self._handle_media_import(file_paths)

    def _import_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Import Media Folder")
        if folder_path and project_manager.current_project:
            new_paths = []
            valid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wav', '.mp3', '.aac', '.png', '.jpg', '.jpeg', '.webp'}
            
            for root, _, files in os.walk(folder_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        new_paths.append(os.path.join(root, f).replace('\\', '/'))
                        
            if new_paths:
                self._handle_media_import(new_paths)
                
    def _handle_media_import(self, file_paths):
        """Processes imports, automatically copying files into the project folder if the setting is enabled."""
        new_paths = []
        copy_enabled = app_config.get_setting("copy_media_to_project", False)
        
        # Derive project folder path directly from where the current hive file is saved
        proj_dir = os.path.dirname(project_manager.project_path) if project_manager.project_path else None
        
        media_dir = None
        if copy_enabled and proj_dir:
            media_dir = os.path.join(proj_dir, "media")
            os.makedirs(media_dir, exist_ok=True)
            
        for path in file_paths:
            path = path.replace('\\', '/')
            final_path = path
            
            # Copy logic
            if copy_enabled and media_dir:
                filename = os.path.basename(path)
                dest_path = os.path.join(media_dir, filename).replace('\\', '/')
                
                # Check if it doesn't already exist in the destination or if paths are different
                if not os.path.exists(dest_path) or os.path.abspath(path) != os.path.abspath(dest_path):
                    try:
                        shutil.copy2(path, dest_path)
                        final_path = dest_path
                    except Exception as e:
                        print(f"Failed to copy media file {path}: {e}")
                        
            if final_path not in project_manager.current_project.media_bin:
                project_manager.current_project.media_bin.append(final_path)
                new_paths.append(final_path)
                
        if new_paths:
            self._process_media_files_async(new_paths)
            project_manager.save_project()

    def _process_media_files_async(self, file_paths):
        if not file_paths: return
        
        thread = MediaLoaderThread(file_paths)
        self.active_threads.add(thread)
        
        thread.item_processed.connect(self._add_media_card_to_grid)
        thread.finished.connect(lambda t=thread: self.active_threads.discard(t) if t in getattr(self, 'active_threads', set()) else None)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _add_media_card_to_grid(self, media_info):
        card = DraggableCard(
            title=media_info["name"],
            icon_name=media_info["icon"],
            item_type="media",
            subtype=media_info["type"],
            file_path=media_info["path"],
            thumbnail=media_info["thumbnail"]
        )
        card.add_requested.connect(self.add_item_to_timeline.emit)
        card.preview_requested.connect(self.preview_requested.emit)
        
        self.media_cards[media_info["path"]] = card

        self.media_grid.addWidget(card, self.media_row, self.media_col)
        self.media_col += 1
        if self.media_col > 1:
            self.media_col = 0
            self.media_row += 1

        # Triggers proxy generation for videos immediately after adding to UI
        if media_info["type"] == "video" and app_config.get_setting("auto_proxies", True):
            media_manager.start_proxy_generation(
                media_info["path"],
                on_progress_callback=self._handle_proxy_progress,
                on_finish_callback=self._handle_proxy_finished,
                on_fail_callback=self._handle_proxy_failed 
            )

    def _handle_proxy_progress(self, original_path, percentage):
        if original_path in self.media_cards:
            self.media_cards[original_path].update_proxy_progress(percentage)

    def _handle_proxy_finished(self, original_path, proxy_path):
        if original_path in self.media_cards:
            self.media_cards[original_path].update_proxy_progress(100)
            self.media_cards[original_path].set_proxy_path(proxy_path)
            
    def _handle_proxy_failed(self, original_path, error_msg):
        print(f"Proxy generation failed for {original_path}: {error_msg}")
        if original_path in self.media_cards:
            self.media_cards[original_path].update_proxy_progress(100)

    def _create_preset_tab(self, category, default_icon, placeholders):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        search = QLineEdit()
        search.setPlaceholderText(f"Search {category}...")
        search.setStyleSheet(self.input_style)
        
        filter_combo = QComboBox()
        filter_combo.addItems(["All", "Favorites", "Trending"])
        filter_combo.setStyleSheet(self.input_style)
        filter_combo.setFixedWidth(90)
        
        top_layout.addWidget(search)
        top_layout.addWidget(filter_combo)
        layout.addLayout(top_layout)

        scroll, grid = self._create_grid_scroll()
        
        item_type_map = { "Captions": "caption", "Effects": "effect", "Transitions": "transition" }
        item_type = item_type_map.get(category, "preset")

        col_count = 2
        for i, item_name in enumerate(placeholders):
            row = i // col_count
            col = i % col_count
            card = DraggableCard(item_name, default_icon, item_type, item_name)
            card.add_requested.connect(self.add_item_to_timeline.emit)
            card.preview_requested.connect(self.preview_requested.emit)
            grid.addWidget(card, row, col)

        layout.addWidget(scroll)
        return widget