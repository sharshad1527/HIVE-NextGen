# ui/workspace.py
import qtawesome as qta
import json
import os
import shutil
import re
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QStackedWidget, QWidget, QScrollArea, 
                               QGridLayout, QLineEdit, QComboBox, QFileDialog, QProgressBar, QDialog, QCheckBox, QRubberBand)
from PySide6.QtCore import Qt, QMimeData, Signal, QThread, QPoint, QRect, QSize
from PySide6.QtGui import QDrag, QPixmap, QKeyEvent

from core.media_manager import media_manager
from core.project_manager import project_manager
from core.app_config import app_config
from core.signal_hub import global_signals

class MediaLoaderThread(QThread):
    """Background Thread: Processes heavy files (Copying and Video extraction) without freezing the UI!"""
    item_processed = Signal(dict, str) # dict data, parent_folder
    finished_all = Signal()
    
    def __init__(self, paths, copy_enabled=False, dest_dir=None, parent_folder=None):
        super().__init__()
        self.paths = paths
        self.copy_enabled = copy_enabled
        self.dest_dir = dest_dir
        self.parent_folder = parent_folder
        
    def run(self):
        for path in self.paths:
            final_path = path
            
            if self.copy_enabled and self.dest_dir:
                filename = os.path.basename(path)
                dest_path = os.path.join(self.dest_dir, filename).replace('\\', '/')
                
                if not os.path.exists(dest_path) or os.path.abspath(path) != os.path.abspath(dest_path):
                    try:
                        shutil.copy2(path, dest_path)
                        final_path = dest_path
                    except Exception as e:
                        print(f"Failed to copy media file {path}: {e}")
            
            info = media_manager.process_file(final_path)
            if info:
                self.item_processed.emit(info, self.parent_folder)
                
        self.finished_all.emit()

class MediaGridWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.setFocusPolicy(Qt.StrongFocus) 

    def mousePressEvent(self, event):
        self.setFocus() 
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            self.rubber_band.setGeometry(rect)
            for card in self.findChildren(DraggableCard):
                if card.isVisible():
                    card.is_selected = rect.intersects(card.geometry())
                    card.setStyleSheet(card.selected_style if card.is_selected else card.default_style)
            
    def mouseReleaseEvent(self, event):
        self.rubber_band.hide()
        self.origin = QPoint()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
            for card in self.findChildren(DraggableCard):
                if card.isVisible():
                    card.is_selected = True
                    card.setStyleSheet(card.selected_style)
            event.accept()
        elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
            selected = []
            for card in self.findChildren(DraggableCard):
                if card.isVisible() and card.is_selected:
                    selected.append(card.get_data())
            if selected:
                try:
                    self.parent().parent().parent().parent().add_item_to_timeline.emit({"batch": selected})
                except Exception:
                    pass
            event.accept()
        else:
            super().keyPressEvent(event)

class DraggableCard(QFrame):
    add_requested = Signal(dict)
    preview_requested = Signal(dict)
    card_clicked = Signal(object, object)
    folder_double_clicked = Signal(str)

    def __init__(self, title, icon_name, item_type, subtype="", file_path="", thumbnail=None, duration=0.0):
        super().__init__()
        self.title = title
        self.item_type = item_type
        self.subtype = subtype
        self.file_path = file_path
        self.thumbnail_path = thumbnail
        self.proxy_path = "" 
        self.parent_folder = None
        self.duration = duration  # seconds — used by timeline for clip width

        
        self.setFixedSize(145, 120) 
        self.setCursor(Qt.PointingHandCursor)
        
        self.is_selected = False
        self.default_style = """
            QFrame { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; }
            QFrame:hover { border: 1px solid rgba(230, 107, 44, 0.5); }
        """
        self.selected_style = """
            QFrame { background-color: rgba(26, 26, 26, 0.6); border: 2px solid #e66b2c; border-radius: 8px; }
            QFrame:hover { border: 2px solid #e66b2c; }
        """
        self.setStyleSheet(self.default_style)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)
        
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
            
        self.progress_bar = QProgressBar(self.thumb_lbl)
        self.progress_bar.setGeometry(10, 60, 115, 6) 
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

        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        metrics = self.title_lbl.fontMetrics()
        elided_title = metrics.elidedText(title, Qt.ElideRight, 130)
        self.title_lbl.setText(elided_title)
        self.title_lbl.setStyleSheet("color: #d1d1d1; font-size: 10px; font-weight: bold; background: transparent; border: none;")
        
        layout.addWidget(self.title_lbl)
        
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
            "thumbnail": self.thumbnail_path,
            "duration": self.duration,  # Pre-computed; avoids cv2 on main thread
        }

    def get_selected_siblings(self):
        try:
            parent_widget = self.parent()
            while parent_widget and not hasattr(parent_widget, "layout"):
                parent_widget = parent_widget.parent()
            
            if parent_widget and parent_widget.layout():
                layout = parent_widget.layout()
                siblings = []
                for i in range(layout.count()):
                    widget = layout.itemAt(i).widget()
                    if isinstance(widget, DraggableCard) and getattr(widget, "is_selected", False) and widget.isVisible():
                        siblings.append(widget.get_data())
                return siblings
        except Exception:
            pass
        return []

    def _on_add_clicked(self):
        siblings = self.get_selected_siblings()
        if not self.is_selected or not siblings:
            self.add_requested.emit(self.get_data())
        else:
            self.add_requested.emit({"batch": siblings})

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.position().toPoint()
            modifiers = event.modifiers()
            if not getattr(self, 'is_selected', False) or modifiers:
                self.card_clicked.emit(self, modifiers)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.item_type == "folder":
            self.folder_double_clicked.emit(self.file_path)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or not self.drag_start_pos:
            return
        if (event.position().toPoint() - self.drag_start_pos).manhattanLength() < 5:
            return
            
        drag = QDrag(self)
        mime = QMimeData()
        
        siblings = self.get_selected_siblings()
        if self.is_selected and len(siblings) > 1:
            data = json.dumps({"batch": siblings})
        else:
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

        self.chk_copy_media = QCheckBox("Copy imported media to project directory")
        self.chk_copy_media.setChecked(app_config.get_setting("copy_media_to_project", False))
        content_layout.addWidget(self.chk_copy_media)

        content_layout.addStretch()

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
    media_load_started = Signal()
    media_load_finished = Signal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        
        self.active_threads = set() 
        self.current_folder_path = None
        self.last_clicked_card = None
        self.all_media_cards = [] 
        self.sort_asc = True
        self._bulk_loading = False  # Suppresses per-card filter/sort during preload
        self._pending_batches = 0   # Track outstanding preload batches
        
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
            btn.clicked.connect(lambda checked=False, idx=i: self.switch_tab(idx))
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
        content = MediaGridWidget(self)
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setContentsMargins(10, 10, 10, 10)
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
        self._update_settings_labels(project_data)

    def _open_project_settings(self):
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
            app_config.set_setting("copy_media_to_project", now_copy_enabled)
            
            new_resolution = dialog.get_resolution()
            project_manager.current_project.resolution = new_resolution
            project_manager.current_project.fps = dialog.get_fps()
            
            self._update_settings_labels(project_manager.current_project)
            project_manager.save_project()
            
            # Notify the player to sync its aspect ratio
            global_signals.project_resolution_changed.emit(new_resolution)
            
            if now_copy_enabled and not was_copy_enabled:
                self._retroactively_copy_media()

    def _retroactively_copy_media(self):
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
            project_manager.current_project.media_bin = updated_paths
            
            for track in project_manager.current_project.tracks:
                for clip in track.clips:
                    if clip.file_path:
                        c_abs = os.path.abspath(clip.file_path)
                        if c_abs in path_mapping:
                            clip.file_path = path_mapping[c_abs]

            project_manager.save_project()
            self.load_media_bin_from_paths(updated_paths)
            global_signals.project_loaded.emit(project_manager.current_project)

    def _update_settings_labels(self, project):
        if not project: return
        res = project.resolution
        fps = project.fps
        
        res_str = f"{res[0]}x{res[1]}"
        if res == (3840, 2160): res_str += " (4K)"
        elif res == (1920, 1080): res_str += " (HD)"
        elif res == (1080, 1920): res_str += " (9:16 Vertical)"
        elif res == (1080, 1080): res_str += " (Square)"
            
        self.lbl_res_value.setText(res_str)
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
        layout.setSpacing(10)

        import_layout = QHBoxLayout()
        btn_import_files = QPushButton(qta.icon('mdi6.file-import-outline', color='#e66b2c'), " Import Files")
        btn_import_files.setStyleSheet(self.btn_style_primary)
        btn_import_files.setCursor(Qt.PointingHandCursor)
        btn_import_files.clicked.connect(self._import_media_files)
        
        btn_import_folder = QPushButton(qta.icon('mdi6.folder-plus-outline', color='#d1d1d1'), " Folder")
        btn_import_folder.setStyleSheet(self.btn_style_secondary)
        btn_import_folder.setCursor(Qt.PointingHandCursor)
        btn_import_folder.clicked.connect(self._import_folder)
        
        self.btn_media_up = QPushButton(qta.icon('mdi6.arrow-up-left', color='#d1d1d1'), "")
        self.btn_media_up.setStyleSheet("QPushButton { background: transparent; border: none; font-weight: bold; } QPushButton:hover { color: #ffffff; }")
        self.btn_media_up.setCursor(Qt.PointingHandCursor)
        self.btn_media_up.clicked.connect(self._navigate_media_up)
        self.btn_media_up.hide()
        
        import_layout.addWidget(btn_import_files, stretch=2)
        import_layout.addWidget(btn_import_folder, stretch=1)
        import_layout.addWidget(self.btn_media_up)
        layout.addLayout(import_layout)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(5)
        
        self.search_media = QLineEdit()
        self.search_media.setPlaceholderText("Search media...")
        self.search_media.setStyleSheet(self.input_style)
        self.search_media.textChanged.connect(self._apply_media_filters_and_sort)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Media", "Videos", "Images", "Audio", "Folders"])
        self.filter_combo.setStyleSheet(self.input_style)
        self.filter_combo.currentTextChanged.connect(self._apply_media_filters_and_sort)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Sort: Name", "Sort: Type", "Sort: Date Added"])
        self.sort_combo.setStyleSheet(self.input_style)
        self.sort_combo.currentTextChanged.connect(self._apply_media_filters_and_sort)
        
        self.btn_sort_order = QPushButton(qta.icon('mdi6.sort-alphabetical-ascending', color='#d1d1d1'), "")
        self.btn_sort_order.setStyleSheet(self.btn_style_secondary)
        self.btn_sort_order.setFixedSize(28, 28)
        self.btn_sort_order.setCursor(Qt.PointingHandCursor)
        self.btn_sort_order.clicked.connect(self._toggle_sort_order)
        
        filter_layout.addWidget(self.search_media, stretch=2)
        filter_layout.addWidget(self.filter_combo, stretch=1)
        filter_layout.addWidget(self.sort_combo, stretch=1)
        filter_layout.addWidget(self.btn_sort_order)
        layout.addLayout(filter_layout)

        self.media_scroll, self.media_grid = self._create_grid_scroll()
        layout.addWidget(self.media_scroll)
        return widget

    def clear_media_bin(self):
        while self.media_grid.count():
            item = self.media_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.all_media_cards.clear()

    def load_media_bin_from_paths(self, paths):
        self.clear_media_bin()
        self.current_folder_path = None
        self.btn_media_up.hide()
        
        # Enter bulk loading mode — suppress per-card filter/sort calls
        self._bulk_loading = True
        
        # Collect all folders and their contents recursively for preloading
        all_files_to_process = []
        valid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wav', '.mp3', '.aac', '.png', '.jpg', '.jpeg', '.webp'}
        
        for p in paths:
            if os.path.exists(p) and os.path.isdir(p):
                self._add_folder_card(p)
                # Preload folder contents recursively
                self._preload_folder_contents(p, valid_exts, all_files_to_process)
                
        files_to_process = [p for p in paths if os.path.exists(p) and not os.path.isdir(p)]
        all_files_to_process.extend([(f, None) for f in files_to_process])
        
        if not all_files_to_process:
            self._bulk_loading = False
            self._apply_media_filters_and_sort()
            return
        
        # Group by parent folder for correct card assignment
        by_folder = {}
        for fpath, parent in all_files_to_process:
            if parent not in by_folder:
                by_folder[parent] = []
            by_folder[parent].append(fpath)
        
        # Emit loading signal ONCE for the entire batch
        self._pending_batches = len(by_folder)
        self.media_load_started.emit()
        
        for parent_folder, file_list in by_folder.items():
            self._process_media_files_async(file_list, False, None, parent_folder=parent_folder, suppress_signals=True)
    
    def _preload_folder_contents(self, folder_path, valid_exts, collect_list):
        """Recursively scan a folder and collect all media files + subfolder cards."""
        folder_path = folder_path.replace('\\', '/')
        try:
            for f in os.listdir(folder_path):
                full_path = os.path.join(folder_path, f).replace('\\', '/')
                if os.path.isdir(full_path):
                    self._add_folder_card_with_parent(full_path, folder_path)
                    # Recurse into subfolders
                    self._preload_folder_contents(full_path, valid_exts, collect_list)
                else:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        collect_list.append((full_path, folder_path))
        except Exception:
            pass
    
    def _add_folder_card_with_parent(self, folder_path, parent_folder):
        """Add a folder card with explicit parent_folder for preloading."""
        folder_path = folder_path.replace('\\', '/')
        parent_folder = parent_folder.replace('\\', '/') if parent_folder else None
        if any(c.file_path == folder_path for c in self.all_media_cards):
            return
            
        card = DraggableCard(
            title=os.path.basename(folder_path),
            icon_name='mdi6.folder',
            item_type='folder',
            subtype='folder',
            file_path=folder_path
        )
        card.card_clicked.connect(self._on_media_card_clicked)
        card.folder_double_clicked.connect(self._on_folder_double_clicked)
        card.date_added = os.path.getmtime(folder_path)
        card.parent_folder = parent_folder
        
        self.all_media_cards.append(card)

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
            if not self.current_folder_path:
                if folder_path not in project_manager.current_project.media_bin:
                    project_manager.current_project.media_bin.append(folder_path)
                    project_manager.save_project()
                self._add_folder_card(folder_path)
            else:
                self._refresh_media_view()

    def _navigate_media_up(self):
        if self.current_folder_path:
            parent = os.path.dirname(self.current_folder_path).replace('\\', '/')
            normalized_project_bins = [p.replace('\\', '/') for p in project_manager.current_project.media_bin]
            if any(p.startswith(parent) for p in normalized_project_bins):
                self.current_folder_path = parent if parent in normalized_project_bins else None
            else:
                self.current_folder_path = None
            self._refresh_media_view()

    def _refresh_media_view(self):
        if self.current_folder_path:
            self.btn_media_up.show()
        else:
            self.btn_media_up.hide()
        self._apply_media_filters_and_sort()
            
    def _add_folder_card(self, folder_path):
        folder_path = folder_path.replace('\\', '/')
        if any(c.file_path == folder_path for c in self.all_media_cards):
            return
            
        card = DraggableCard(
            title=os.path.basename(folder_path),
            icon_name='mdi6.folder',
            item_type='folder',
            subtype='folder',
            file_path=folder_path
        )
        card.card_clicked.connect(self._on_media_card_clicked)
        card.folder_double_clicked.connect(self._on_folder_double_clicked)
        card.date_added = os.path.getmtime(folder_path)
        card.parent_folder = self.current_folder_path
        
        self.all_media_cards.append(card)
        if not self._bulk_loading:
            self._apply_media_filters_and_sort()

    def _on_folder_double_clicked(self, folder_path):
        self.current_folder_path = folder_path.replace('\\', '/')
        self.btn_media_up.show()
        # All folder contents are already preloaded — just filter the view
        self._apply_media_filters_and_sort()
                
    def _handle_media_import(self, file_paths):
        copy_enabled = app_config.get_setting("copy_media_to_project", False)
        proj_dir = os.path.dirname(project_manager.project_path) if project_manager.project_path else None
        
        media_dir = None
        if copy_enabled and proj_dir:
            media_dir = os.path.join(proj_dir, "media")
            os.makedirs(media_dir, exist_ok=True)
            
        self._process_media_files_async(file_paths, copy_enabled, media_dir, parent_folder=self.current_folder_path)

    def _process_media_files_async(self, file_paths, copy_enabled=False, dest_dir=None, parent_folder=None, suppress_signals=False):
        if not file_paths: return
        if not suppress_signals:
            self._pending_batches = 1
            self.media_load_started.emit()
        
        thread = MediaLoaderThread(file_paths, copy_enabled, dest_dir, parent_folder)
        self.active_threads.add(thread)
        
        thread.item_processed.connect(self._add_media_card_to_grid)
        thread.finished_all.connect(self._on_import_batch_finished)
        
        thread.finished.connect(lambda t=thread: self.active_threads.discard(t) if t in getattr(self, 'active_threads', set()) else None)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_import_batch_finished(self):
        self._pending_batches = max(0, self._pending_batches - 1)
        
        if self._pending_batches <= 0:
            # All batches done — exit bulk mode, do one final filter pass, save
            self._bulk_loading = False
            self._apply_media_filters_and_sort()
            project_manager.save_project()
            self.media_load_finished.emit()

    def _add_media_card_to_grid(self, media_info, parent_folder):
        final_path = media_info["path"].replace('\\', '/')
        
        if parent_folder is None and final_path not in project_manager.current_project.media_bin:
            project_manager.current_project.media_bin.append(final_path)

        if any(c.file_path == final_path for c in self.all_media_cards):
            return

        card = DraggableCard(
            title=media_info["name"],
            icon_name=media_info["icon"],
            item_type="media",
            subtype=media_info["type"],
            file_path=final_path,
            thumbnail=media_info["thumbnail"],
            duration=media_info.get("duration", 0.0),
        )
        card.date_added = os.path.getmtime(final_path) if os.path.exists(final_path) else 0
        card.parent_folder = parent_folder.replace('\\', '/') if parent_folder else None
        
        card.add_requested.connect(self.add_item_to_timeline.emit)
        card.preview_requested.connect(self.preview_requested.emit)
        card.card_clicked.connect(self._on_media_card_clicked)
        
        self.all_media_cards.append(card)
        if not self._bulk_loading:
            self._apply_media_filters_and_sort()

        if media_info["type"] == "video" and app_config.get_setting("auto_proxies", True):
            media_manager.start_proxy_generation(
                final_path,
                on_progress_callback=self._handle_proxy_progress,
                on_finish_callback=self._handle_proxy_finished,
                on_fail_callback=self._handle_proxy_failed 
            )

    def _toggle_sort_order(self):
        self.sort_asc = not self.sort_asc
        icon = 'mdi6.sort-alphabetical-ascending' if self.sort_asc else 'mdi6.sort-alphabetical-descending'
        self.btn_sort_order.setIcon(qta.icon(icon, color='#d1d1d1'))
        self._apply_media_filters_and_sort()

    def _apply_media_filters_and_sort(self):
        search_txt = self.search_media.text().lower()
        filter_txt = self.filter_combo.currentText()
        sort_txt = self.sort_combo.currentText()
        
        def natural_sort_key(card):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', card.title)]
            
        curr_pf = self.current_folder_path.replace('\\', '/') if self.current_folder_path else None
        
        visible_cards = []
        for card in self.all_media_cards:
            card_pf = card.parent_folder.replace('\\', '/') if card.parent_folder else None
            
            # 0. Folder Location Filter
            if card_pf != curr_pf:
                card.hide()
                continue

            # 1. Type Filter
            matches_filter = True
            if filter_txt == "Videos" and card.subtype != "video": matches_filter = False
            elif filter_txt == "Images" and card.subtype != "image": matches_filter = False
            elif filter_txt == "Audio" and card.subtype != "audio": matches_filter = False
            elif filter_txt == "Folders" and card.item_type != "folder": matches_filter = False
            
            # 2. Search Filter (Text and Numbers)
            matches_search = (search_txt in card.title.lower()) if search_txt else True
            
            if matches_filter and matches_search:
                visible_cards.append(card)
                card.show()
            else:
                card.hide()
                card.is_selected = False
                card.setStyleSheet(card.default_style)
                
        # 3. Sort Execution
        if "Name" in sort_txt:
            visible_cards.sort(key=natural_sort_key, reverse=not self.sort_asc)
        elif "Type" in sort_txt:
            visible_cards.sort(key=lambda c: c.subtype, reverse=not self.sort_asc)
        elif "Date" in sort_txt:
            visible_cards.sort(key=lambda c: getattr(c, "date_added", 0), reverse=not self.sort_asc)
            
        while self.media_grid.count():
            self.media_grid.takeAt(0)
            
        row, col = 0, 0
        for card in visible_cards:
            self.media_grid.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

    def _on_media_card_clicked(self, card, modifiers):
        all_visible = [c for c in self.all_media_cards if c.isVisible()]
                
        if modifiers & Qt.ControlModifier:
            card.is_selected = not card.is_selected
            card.setStyleSheet(card.selected_style if card.is_selected else card.default_style)
            self.last_clicked_card = card
        elif modifiers & Qt.ShiftModifier and self.last_clicked_card:
            try:
                idx1 = all_visible.index(self.last_clicked_card)
                idx2 = all_visible.index(card)
                start, end = min(idx1, idx2), max(idx1, idx2)
                for i in range(start, end + 1):
                    all_visible[i].is_selected = True
                    all_visible[i].setStyleSheet(all_visible[i].selected_style)
            except ValueError:
                pass
        else:
            for c in all_visible:
                if c != card:
                    c.is_selected = False
                    c.setStyleSheet(c.default_style)
            card.is_selected = True
            card.setStyleSheet(card.selected_style)
            self.last_clicked_card = card

    def _handle_proxy_progress(self, original_path, percentage):
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(percentage)

    def _handle_proxy_finished(self, original_path, proxy_path):
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(100)
                card.set_proxy_path(proxy_path)
            
    def _handle_proxy_failed(self, original_path, error_msg):
        print(f"Proxy generation failed for {original_path}: {error_msg}")
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(100)

    def _create_preset_tab(self, category, default_icon, placeholders):
        from core.preset_loader import get_presets
        
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
        category_folder_map = { "Captions": "captions", "Effects": "effects", "Transitions": "transitions" }
        item_type = item_type_map.get(category, "preset")
        folder_name = category_folder_map.get(category, category.lower())

        presets = get_presets(folder_name)
        
        if not presets:
            presets = [{"name": name, "icon": default_icon, "properties": {}} for name in placeholders]

        col_count = 2
        all_cards = []
        for i, preset in enumerate(presets):
            row = i // col_count
            col = i % col_count
            preset_name = preset.get("name", "Unnamed")
            preset_icon = preset.get("icon", default_icon)
            
            card = DraggableCard(preset_name, preset_icon, item_type, preset_name)
            card._preset_properties = preset.get("properties", {})
            
            original_get_data = card.get_data
            def make_enhanced_get_data(orig, props):
                def enhanced_get_data():
                    data = orig()
                    data["preset_properties"] = props
                    return data
                return enhanced_get_data
            card.get_data = make_enhanced_get_data(original_get_data, card._preset_properties)
            
            card.add_requested.connect(self.add_item_to_timeline.emit)
            card.preview_requested.connect(self.preview_requested.emit)
            grid.addWidget(card, row, col)
            all_cards.append(card)

        def filter_presets(text):
            text_lower = text.lower()
            row_idx, col_idx = 0, 0
            for card in all_cards:
                matches = text_lower in card.title.lower() if text_lower else True
                card.setVisible(matches)
                if matches:
                    grid.removeWidget(card)
                    grid.addWidget(card, row_idx // col_count, row_idx % col_count)
                    row_idx += 1
                    
        search.textChanged.connect(filter_presets)

        layout.addWidget(scroll)
        return widget