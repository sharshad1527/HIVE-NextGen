# ui/settings_dialog.py
import qtawesome as qta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QWidget, QStackedWidget, QListWidget, 
                               QListWidgetItem, QLineEdit, QFileDialog, QMessageBox,
                               QComboBox, QSpinBox, QCheckBox, QDoubleSpinBox, QFrame,
                               QScrollArea)
from PySide6.QtCore import Qt, QSize
from core.app_config import app_config

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Global Settings")
        self.setFixedSize(700, 500)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #111111;
                border: 1px solid #262626;
                border-radius: 10px;
            }
            QLabel { color: #d1d1d1; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; color: #808080; padding: 6px 10px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
            QCheckBox { color: #d1d1d1; font-weight: bold; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); }
            QCheckBox::indicator:checked { background-color: #e66b2c; border: 1px solid #e66b2c; image: url(none); } /* Optional checkmark bg */
            
            QListWidget {
                background-color: transparent; border: none; outline: none;
            }
            QListWidget::item {
                color: #808080; font-size: 13px; font-weight: bold; padding: 12px;
                border-radius: 6px; margin-bottom: 5px;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.05); color: #ffffff;
            }
            QListWidget::item:selected {
                background-color: rgba(230, 107, 44, 0.1); color: #e66b2c;
                border: 1px solid rgba(230, 107, 44, 0.3);
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1;
                border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); color: #ffffff; }
            
            QFrame#Separator { background-color: rgba(255, 255, 255, 0.05); }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)

        # Title Bar
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #151515; border-bottom: 1px solid #262626; border-top-left-radius: 10px; border-top-right-radius: 10px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        lbl_title = QLabel("Settings")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff; border: none;")
        
        btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #ff3b30; border-radius: 4px; }")
        btn_close.clicked.connect(self.close)
        
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()
        title_layout.addWidget(btn_close)
        main_layout.addWidget(title_bar)

        # Content Splitter
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(20)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(150)
        for tab_name in ["General", "Editing", "Export", "Performance"]:
            item = QListWidgetItem(tab_name)
            self.sidebar.addItem(item)
        
        self.sidebar.currentRowChanged.connect(self.change_page)

        # Stacked Widget (Pages)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.create_general_page())
        self.stack.addWidget(self.create_editing_page())
        self.stack.addWidget(self.create_export_page())
        self.stack.addWidget(self.create_performance_page())

        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.stack)
        main_layout.addLayout(content_layout)

        self.sidebar.setCurrentRow(0)

    def change_page(self, index):
        self.stack.setCurrentIndex(index)

    def _create_separator(self):
        sep = QFrame()
        sep.setObjectName("Separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        return sep
        
    def _create_row(self, layout, label_text, widget):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("font-weight: bold;")
        row.addWidget(lbl)
        row.addStretch()
        widget.setFixedWidth(200)
        row.addWidget(widget)
        layout.addLayout(row)
        return widget

    def create_general_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        lbl_header2 = QLabel("Timeline Defaults")
        lbl_header2.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        layout.addWidget(lbl_header2)

        # Image Duration
        spin_img = QDoubleSpinBox()
        spin_img.setRange(0.1, 60.0)
        spin_img.setSuffix(" sec")
        spin_img.setValue(app_config.get_setting("default_image_duration"))
        spin_img.valueChanged.connect(lambda v: app_config.set_setting("default_image_duration", v))
        self._create_row(layout, "Default Image Duration:", spin_img)

        # Transition Duration
        spin_trans = QDoubleSpinBox()
        spin_trans.setRange(0.1, 10.0)
        spin_trans.setSuffix(" sec")
        spin_trans.setValue(app_config.get_setting("default_transition_duration"))
        spin_trans.valueChanged.connect(lambda v: app_config.set_setting("default_transition_duration", v))
        self._create_row(layout, "Default Transition Duration:", spin_trans)

        return page

    def create_editing_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        lbl_header = QLabel("Project & Editing")
        lbl_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        layout.addWidget(lbl_header)

        # Project Path
        lbl_desc = QLabel("Default location for saving new .hive projects:")
        lbl_desc.setStyleSheet("color: #808080; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        path_layout = QHBoxLayout()
        self.path_input = QLineEdit(str(app_config.default_project_path))
        self.path_input.setReadOnly(True)
        btn_browse = QPushButton(qta.icon('mdi6.folder-outline', color='#d1d1d1'), " Browse")
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self.browse_project_path)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)
        
        layout.addWidget(self._create_separator())

        # Copy Media Option
        chk_copy_media = QCheckBox("Copy imported media to project directory")
        chk_copy_media.setChecked(app_config.get_setting("copy_media_to_project", False))
        chk_copy_media.stateChanged.connect(lambda v: app_config.set_setting("copy_media_to_project", bool(v)))
        layout.addWidget(chk_copy_media)

        # Auto-Save
        chk_autosave = QCheckBox("Enable Background Auto-Save")
        chk_autosave.setChecked(app_config.get_setting("auto_save_enabled"))
        chk_autosave.stateChanged.connect(lambda v: app_config.set_setting("auto_save_enabled", bool(v)))
        layout.addWidget(chk_autosave)

        spin_autosave = QSpinBox()
        spin_autosave.setRange(1, 60)
        spin_autosave.setSuffix(" minutes")
        spin_autosave.setValue(app_config.get_setting("auto_save_interval"))
        spin_autosave.valueChanged.connect(lambda v: app_config.set_setting("auto_save_interval", v))
        self._create_row(layout, "Auto-Save Interval:", spin_autosave)
        
        layout.addWidget(self._create_separator())
        
        lbl_header2 = QLabel("New Project Defaults")
        lbl_header2.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(lbl_header2)

        # Resolution
        cb_res = QComboBox()
        cb_res.addItems(["3840x2160 (4K)", "1920x1080 (HD)", "1080x1920 (9:16 Vertical)", "1080x1080 (Square)"])
        cb_res.setCurrentText(app_config.get_setting("default_resolution"))
        cb_res.currentTextChanged.connect(lambda v: app_config.set_setting("default_resolution", v))
        self._create_row(layout, "Resolution / Aspect Ratio:", cb_res)

        # FPS
        cb_fps = QComboBox()
        cb_fps.addItems(["23.976", "24", "25", "29.97", "30", "50", "60"])
        cb_fps.setCurrentText(app_config.get_setting("default_fps"))
        cb_fps.currentTextChanged.connect(lambda v: app_config.set_setting("default_fps", v))
        self._create_row(layout, "Frame Rate (FPS):", cb_fps)

        return page

    def create_export_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        lbl_header = QLabel("Export Settings")
        lbl_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        layout.addWidget(lbl_header)

        # Export Path
        lbl_desc = QLabel("Default directory to save exported videos:")
        lbl_desc.setStyleSheet("color: #808080; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        path_layout = QHBoxLayout()
        self.export_path_input = QLineEdit(str(app_config.default_export_path))
        self.export_path_input.setReadOnly(True)
        btn_browse_export = QPushButton(qta.icon('mdi6.folder-outline', color='#d1d1d1'), " Browse")
        btn_browse_export.setCursor(Qt.PointingHandCursor)
        btn_browse_export.clicked.connect(self.browse_export_path)
        path_layout.addWidget(self.export_path_input)
        path_layout.addWidget(btn_browse_export)
        layout.addLayout(path_layout)
        
        layout.addWidget(self._create_separator())

        # Format
        cb_format = QComboBox()
        cb_format.addItems(["MP4", "MOV", "MKV", "GIF"])
        cb_format.setCurrentText(app_config.get_setting("export_format"))
        cb_format.currentTextChanged.connect(lambda v: app_config.set_setting("export_format", v))
        self._create_row(layout, "Default Format:", cb_format)
        
        # Codec
        cb_codec = QComboBox()
        cb_codec.addItems(["H.264 (High Compatibility)", "HEVC / H.265 (High Efficiency)", "Apple ProRes 422", "AV1"])
        cb_codec.setCurrentText(app_config.get_setting("export_codec"))
        cb_codec.currentTextChanged.connect(lambda v: app_config.set_setting("export_codec", v))
        self._create_row(layout, "Video Codec:", cb_codec)

        return page

    def create_performance_page(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #131313; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #555; }
            QScrollBar:horizontal { background: #131313; height: 10px; margin: 0px; }
            QScrollBar::handle:horizontal { background: #333; border-radius: 5px; }
            QScrollBar::handle:horizontal:hover { background: #555; }
        """)

        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        lbl_header = QLabel("Performance & Render")
        lbl_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 5px;")
        layout.addWidget(lbl_header)

        chk_gpu = QCheckBox("Enable Hardware Acceleration (GPU Decoding/Encoding)")
        chk_gpu.setChecked(app_config.get_setting("hardware_acceleration"))
        chk_gpu.stateChanged.connect(lambda v: app_config.set_setting("hardware_acceleration", bool(v)))
        layout.addWidget(chk_gpu)
        
        lbl_gpu_desc = QLabel("Improves playback and export times utilizing NVENC/VideoToolbox.")
        lbl_gpu_desc.setStyleSheet("color: #808080; font-size: 11px; margin-left: 25px;")
        lbl_gpu_desc.setWordWrap(True)
        layout.addWidget(lbl_gpu_desc)
        
        layout.addWidget(self._create_separator())
        
        lbl_header2 = QLabel("Proxy Media")
        lbl_header2.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(lbl_header2)

        chk_proxy = QCheckBox("Auto-generate proxy media for 4K/Heavy files")
        chk_proxy.setChecked(app_config.get_setting("auto_proxies"))
        chk_proxy.stateChanged.connect(lambda v: app_config.set_setting("auto_proxies", bool(v)))
        layout.addWidget(chk_proxy)

        cb_proxy_res = QComboBox()
        cb_proxy_res.addItems(["360p", "540p", "720p"])
        cb_proxy_res.setCurrentText(app_config.get_setting("proxy_resolution"))
        cb_proxy_res.currentTextChanged.connect(lambda v: app_config.set_setting("proxy_resolution", v))
        self._create_row(layout, "Proxy Resolution:", cb_proxy_res)

        layout.addWidget(self._create_separator())

        # Cache Size Row
        lbl_header3 = QLabel("Cache Management")
        lbl_header3.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff; margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(lbl_header3)

        lbl_cache_desc = QLabel("Clearing the cache deletes temporary render files and proxy media.\nProjects will safely regenerate them when reopened.")
        lbl_cache_desc.setStyleSheet("color: #808080; font-size: 11px; margin-bottom: 10px;")
        lbl_cache_desc.setWordWrap(True)
        layout.addWidget(lbl_cache_desc)

        size_layout = QHBoxLayout()
        self.lbl_cache_size = QLabel(f"Current Cache Size:  {app_config.calculate_cache_size()}")
        self.lbl_cache_size.setStyleSheet("font-size: 14px; font-weight: bold; color: #d1d1d1;")
        
        btn_clear = QPushButton(qta.icon('mdi6.trash-can-outline', color='#ffffff'), " Clear Cache")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 59, 48, 0.8); color: #ffffff; border: none;
                border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ff3b30; }
        """)
        btn_clear.clicked.connect(self.clear_cache)

        size_layout.addWidget(self.lbl_cache_size)
        size_layout.addStretch()
        size_layout.addWidget(btn_clear)
        layout.addLayout(size_layout)

        scroll_area.setWidget(page)
        return scroll_area

    def browse_project_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Default Project Folder", str(app_config.default_project_path))
        if dir_path:
            app_config.set_default_project_path(dir_path)
            self.path_input.setText(str(app_config.default_project_path))
            
    def browse_export_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Default Export Folder", str(app_config.default_export_path))
        if dir_path:
            app_config.set_default_export_path(dir_path)
            self.export_path_input.setText(str(app_config.default_export_path))

    def clear_cache(self):
        freed = app_config.clear_cache()
        self.lbl_cache_size.setText(f"Current Cache Size:  {app_config.calculate_cache_size()}")
        QMessageBox.information(self, "Cache Cleared", f"Successfully freed {freed} of space.")