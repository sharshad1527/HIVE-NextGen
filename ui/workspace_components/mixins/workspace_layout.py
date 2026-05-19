import qtawesome as qta
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, 
                               QPushButton, QLabel, QScrollArea, QGridLayout, QFrame)
from PySide6.QtCore import Qt
from ui.workspace_components.media_grid import MediaGridWidget
from core.logger import hive_logger as logger

class WorkspaceLayoutMixin:
    """Mixin for workspace layout and UI component creation."""
    def switch_tab(self, index):
        logger.info(f"Workspace: Switching to tab {index}")
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
