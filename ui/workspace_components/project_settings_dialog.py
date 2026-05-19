import qtawesome as qta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, 
                               QLabel, QPushButton, QComboBox, QCheckBox)
from PySide6.QtCore import Qt

from core.app_config import app_config
from core.project_manager import project_manager
from core.logger import hive_logger as logger

class ProjectSettingsDialog(QDialog):
    """Dialog for configuring project-wide settings like resolution and frame rate."""
    def __init__(self, current_res, current_fps, parent=None):
        super().__init__(parent)
        logger.debug(f"Opening ProjectSettingsDialog: res={current_res}, fps={current_fps}")
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
        btn_close.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #ff3b30; }")
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

    def accept(self):
        logger.info(f"ProjectSettingsDialog: Saving settings (res={self.get_resolution()}, fps={self.get_fps()}, copy={self.chk_copy_media.isChecked()})")
        super().accept()

    def get_resolution(self):
        return self.res_options[self.cb_res.currentText()]

    def get_fps(self):
        return float(self.cb_fps.currentText())
