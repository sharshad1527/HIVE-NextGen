import os
import json
import qtawesome as qta
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QWidget, QLabel, 
                               QProgressBar, QPushButton)
from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtGui import QDrag, QPixmap

from core.media_manager import media_manager
from core.logger import hive_logger as logger

class DraggableCard(QFrame):
    """A draggable UI component representing a media item, effect, or folder."""
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
        self.duration = duration

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
            "duration": self.duration,
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
        except Exception as e:
            logger.debug(f"DraggableCard: Failed to get siblings: {e}")
        return []

    def _on_add_clicked(self):
        siblings = self.get_selected_siblings()
        if not self.is_selected or not siblings:
            logger.info(f"DraggableCard: Add requested for {self.title}")
            self.add_requested.emit(self.get_data())
        else:
            logger.info(f"DraggableCard: Batch add requested for {len(siblings)} items")
            self.add_requested.emit({"batch": siblings})

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.position().toPoint()
            modifiers = event.modifiers()
            if not getattr(self, 'is_selected', False) or modifiers:
                self.card_clicked.emit(self, modifiers)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.item_type == "folder":
            logger.debug(f"DraggableCard: Folder double-clicked: {self.file_path}")
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
            logger.debug(f"DraggableCard: Starting batch drag for {len(siblings)} items")
            data = json.dumps({"batch": siblings})
        else:
            logger.debug(f"DraggableCard: Starting drag for {self.title}")
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
            logger.debug(f"DraggableCard: Preview requested for {self.title}")
            self.preview_requested.emit(self.get_data())
        self.drag_start_pos = None
