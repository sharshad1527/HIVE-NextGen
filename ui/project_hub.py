# ui/project_hub.py
import qtawesome as qta
import random
import os
import sys
import subprocess
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QFrame, QGridLayout, QLineEdit, 
                               QSpacerItem, QSizePolicy, QToolButton, QButtonGroup,
                               QStackedWidget, QScrollArea)
from PySide6.QtCore import Qt, QPoint, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QImage, QPixmap
from PySide6.QtWidgets import QInputDialog, QMessageBox
from PySide6.QtGui import QPixmap

from core.project_manager import project_manager
from core.app_config import app_config 
from ui.settings_dialog import SettingsDialog
from utils.paths import get_asset_path
from ui.about_dialog import AboutDialog, ClickableLabel

class HubSidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(85)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.sidebar_box = QFrame()
        self.sidebar_box.setStyleSheet("""
            QFrame { background-color: rgba(14, 14, 16, 0.90); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; }
        """)
        sidebar_layout = QVBoxLayout(self.sidebar_box)
        sidebar_layout.setContentsMargins(0, 7, 0, 15) 
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # self.lbl_logo = QLabel("H.")
        # self.lbl_logo.setFixedSize(85, 44) 
        # self.lbl_logo.setAlignment(Qt.AlignCenter)
        # self.lbl_logo.setStyleSheet("color: #e66b2c; font-size: 20px; font-weight: 900; font-style: italic; background: transparent; border: none;")
        # sidebar_layout.addWidget(self.lbl_logo, 0, Qt.AlignHCenter)

        # Logo
        self.lbl_logo = ClickableLabel()
        self.lbl_logo.setFixedSize(85, 44) 
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        self.lbl_logo.setStyleSheet("background-color: transparent; border: none;")
        logo_path = get_asset_path("logos", "HIVE_Logo_Mark.svg")
        pixmap = QPixmap(logo_path)
        scaled_pixmap = pixmap.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_logo.setPixmap(scaled_pixmap)
        sidebar_layout.addWidget(self.lbl_logo, 0, Qt.AlignHCenter)
        sidebar_layout.addSpacing(10)
        self.lbl_logo.clicked.connect(self.show_about_dialog)


        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.btn_home = self._create_icon_button("mdi6.home-variant-outline", "Home", True)
        self.btn_templates = self._create_icon_button("mdi6.view-dashboard-outline", "Templates")
        self.btn_trash = self._create_icon_button("mdi6.trash-can-outline", "Trash")
        
        sidebar_layout.addWidget(self.btn_home, 0, Qt.AlignHCenter)
        sidebar_layout.addWidget(self.btn_templates, 0, Qt.AlignHCenter)
        sidebar_layout.addWidget(self.btn_trash, 0, Qt.AlignHCenter)

        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        sidebar_layout.addItem(spacer)

        self.btn_settings = self._create_icon_button("mdi6.cog-outline", "Settings")
        sidebar_layout.addWidget(self.btn_settings, 0, Qt.AlignHCenter)
        layout.addWidget(self.sidebar_box)

    def _create_icon_button(self, icon_name, text, checked=False):
        btn = QToolButton() 
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setText(text)
        btn.setIcon(qta.icon(icon_name, color='#808080', color_active='#e66b2c'))
        btn.setIconSize(QSize(22, 22))
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(70, 60)
        btn.setStyleSheet("""
            QToolButton { background-color: transparent; border: 1px solid transparent; border-radius: 8px; color: #808080; font-size: 10px; font-weight: 600; padding-top: 6px; padding-bottom: 4px; }
            QToolButton:hover { background-color: rgba(255, 255, 255, 0.05); color: #ffffff; }
            QToolButton:checked { background-color: rgba(230, 107, 44, 0.1); border: 1px solid rgba(230, 107, 44, 0.3); color: #e66b2c; }
        """)
        self.btn_group.addButton(btn)
        return btn

    def open_trash_bin(self):
        """Opens the hidden .bin directory in the user's OS file explorer."""
        bin_dir = os.path.join(app_config.default_project_path, ".bin")
        os.makedirs(bin_dir, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(bin_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", bin_dir])
            else:
                subprocess.Popen(["xdg-open", bin_dir])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open trash bin: {e}")

    def show_about_dialog(self):
        """Create and show the pop-up"""
        dialog = AboutDialog(self)
        dialog.exec()

class HubTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.parent_window = parent
        self.dragPos = QPoint()
        self.setStyleSheet("background-color: rgba(22, 22, 24, 0.85); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 12px;")

        layout = QGridLayout(self)
        layout.setContentsMargins(15, 0, 15, 0)

        self.lbl_title = QLabel("H.I.V.E - Project Hub")
        self.lbl_title.setStyleSheet("color: #808080; font-size: 12px; font-weight: bold; letter-spacing: 1px; border: none; background: transparent;")
        layout.addWidget(self.lbl_title, 0, 0, Qt.AlignLeft)

        right_widget = QWidget()
        right_widget.setStyleSheet("border: none; background: transparent;")
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet("QPushButton { background: transparent; border: none; border-radius: 4px; } QPushButton:hover { background-color: #ff3b30; }")
        self.btn_close.clicked.connect(self.parent_window.close)
        
        right_layout.addWidget(self.btn_close)
        layout.addWidget(right_widget, 0, 2, Qt.AlignRight)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.parent_window.move(self.parent_window.pos() + event.globalPosition().toPoint() - self.dragPos)
            self.dragPos = event.globalPosition().toPoint()
            event.accept()

class ProjectHubWindow(QMainWindow):
    # Signals for main.py to handle file dialogs
    create_project_requested = Signal(str) # Emits 'standard' or 'automated'
    open_project_requested = Signal(str)   # Emits 'filepath' or '' to open dialog

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)
        self.resize(1150, 720) # Increased size to prevent scrollbars and accommodate cards easily
        self._generate_premium_background_texture()
        self.setup_ui()

    def _generate_premium_background_texture(self):
        size = 128
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        for y in range(size):
            for x in range(size):
                if random.random() > 0.25:
                    intensity = random.randint(0, 18)
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

        self.sidebar = HubSidebar()
        main_layout.addWidget(self.sidebar)

        self.sidebar.btn_settings.clicked.connect(self.open_settings)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        self.title_bar = HubTitleBar(self)
        content_layout.addWidget(self.title_bar)
        
        # We use a StackedWidget to seamlessly switch between Recent Projects and the Trash Bin
        self.content_stack = QStackedWidget()
        content_layout.addWidget(self.content_stack)
        
        # ===== PAGE 0: HOME =====
        self.page_home = QWidget()
        home_layout = QVBoxLayout(self.page_home)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(15)

        # Start Creating Section
        lbl_start = QLabel("Start Creating")
        lbl_start.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; margin-top: 10px;")
        home_layout.addWidget(lbl_start)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)
        
        btn_standard = self._create_action_card("Standard Project", "Timeline-based manual editing workspace", 'mdi6.movie-open-play-outline')
        btn_standard.clicked.connect(lambda: self.create_project_requested.emit("standard"))
        
        btn_automated = self._create_action_card("Automated Project", "Script-driven automated generation pipeline", 'mdi6.auto-fix')
        btn_automated.clicked.connect(lambda: self.create_project_requested.emit("automated"))
        
        cards_layout.addWidget(btn_standard)
        cards_layout.addWidget(btn_automated)
        home_layout.addLayout(cards_layout)

        # Recent Projects Section
        recent_header = QHBoxLayout()
        lbl_recent = QLabel("Recent Projects")
        lbl_recent.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; margin-top: 15px;")
        
        btn_open = QPushButton(qta.icon("mdi6.folder-open-outline", color="#d1d1d1"), " Open Project...")
        btn_open.setStyleSheet("""
            QPushButton { background-color: rgba(255, 255, 255, 0.05); color: #d1d1d1; font-weight: bold; padding: 6px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); margin-top: 15px; }
            QPushButton:hover { background-color: rgba(255,255,255,0.1); border: 1px solid #e66b2c; color: #ffffff;}
        """)
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(lambda: self.open_project_requested.emit("")) # Empty string triggers file browser

        search_bar = QLineEdit()
        search_bar.setPlaceholderText("Search projects...")
        search_bar.setFixedWidth(200)
        search_bar.setStyleSheet("""
            QLineEdit { background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; color: #d1d1d1; padding: 6px 10px; margin-top: 15px; }
            QLineEdit:focus { border: 1px solid #e66b2c; }
        """)
        
        recent_header.addWidget(lbl_recent)
        recent_header.addStretch()
        recent_header.addWidget(btn_open)
        recent_header.addWidget(search_bar)
        home_layout.addLayout(recent_header)

        # Scroll Area for Grid (Fixed horizontal scroller issue)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 4px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #555; }
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        
        # Grid for dynamic recent items
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_content)
        home_layout.addWidget(self.scroll_area)
        
        self.content_stack.addWidget(self.page_home)
        
        # ===== PAGE 1: TRASH =====
        self.page_trash = QWidget()
        trash_layout = QVBoxLayout(self.page_trash)
        trash_layout.setContentsMargins(0, 0, 0, 0)
        trash_layout.setSpacing(15)

        trash_header = QLabel("Trash Bin")
        trash_header.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; margin-top: 10px;")
        trash_sub = QLabel("Items here will be permanently deleted after 7 days.")
        trash_sub.setStyleSheet("color: #808080; font-size: 12px;")
        
        trash_layout.addWidget(trash_header)
        trash_layout.addWidget(trash_sub)

        self.trash_scroll = QScrollArea()
        self.trash_scroll.setWidgetResizable(True)
        self.trash_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.trash_scroll.setStyleSheet(self.scroll_area.styleSheet())

        self.trash_content = QWidget()
        self.trash_content.setStyleSheet("background: transparent;")
        self.trash_grid = QGridLayout(self.trash_content)
        self.trash_grid.setSpacing(15)
        self.trash_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.trash_scroll.setWidget(self.trash_content)
        trash_layout.addWidget(self.trash_scroll)

        self.content_stack.addWidget(self.page_trash)
        
        main_layout.addWidget(content_widget)
        
        # Connect Sidebar page switching
        self.sidebar.btn_home.clicked.connect(lambda: self.switch_page(0))
        self.sidebar.btn_trash.clicked.connect(lambda: self.switch_page(1))

    def switch_page(self, index):
        self.content_stack.setCurrentIndex(index)
        if index == 0:
            self.refresh_recent_projects()
        elif index == 1:
            self.refresh_trash()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

        # Optional: If you want to uncheck the settings button after closing
        self.sidebar.btn_settings.setChecked(False)
        
    def refresh_trash(self):
        """Pulls trashed items and updates the trash grid."""
        while self.trash_grid.count():
            item = self.trash_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        trashed_items = project_manager.get_trashed_projects()
        if not trashed_items:
            empty_lbl = QLabel("Trash is currently empty.")
            empty_lbl.setStyleSheet("color: #808080; font-style: italic;")
            self.trash_grid.addWidget(empty_lbl, 0, 0)
            return

        row, col = 0, 0
        for data in trashed_items:
            card = self._create_trash_card(data["name"], data["days_left"], data["path"])
            self.trash_grid.addWidget(card, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1

    def refresh_recent_projects(self):
        """Clears the grid and pulls the latest projects from memory."""
        # Clean existing items
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        recents = app_config.get_recent_projects()
        
        if not recents:
            empty_lbl = QLabel("No recent projects found. Create a new one above or open an existing .hive file!")
            empty_lbl.setStyleSheet("color: #808080; font-style: italic;")
            self.grid_layout.addWidget(empty_lbl, 0, 0)
            return

        row, col = 0, 0
        for data in recents: # Loop dynamically through all
            card = self._create_recent_card(data["name"], data["date"], data.get("duration", "00:00:00:00"), data["path"])
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col > 3:
                col = 0
                row += 1

    def _create_action_card(self, title, subtitle, icon_name):
        btn = QPushButton()
        btn.setFixedHeight(120)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; text-align: left; padding: 20px; }
            QPushButton:hover { background-color: rgba(34, 34, 34, 0.8); border: 1px solid #e66b2c; }
        """)
        
        layout = QHBoxLayout(btn)
        layout.setSpacing(15)
        
        icon_box = QLabel()
        icon_box.setPixmap(qta.icon(icon_name, color='#e66b2c').pixmap(36, 36))
        icon_box.setStyleSheet("background: rgba(230, 107, 44, 0.1); border-radius: 8px; padding: 10px;")
        layout.addWidget(icon_box)
        
        text_layout = QVBoxLayout()
        text_layout.setAlignment(Qt.AlignVCenter)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold; background: transparent; border: none;")
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #808080; font-size: 12px; background: transparent; border: none;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(sub_lbl)
        layout.addLayout(text_layout)
        layout.addStretch()
        return btn

    def _create_recent_card(self, name, date, duration, file_path):
        card = QPushButton()
        card.setFixedSize(210, 160)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet("""
            QPushButton { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; text-align: left; }
            QPushButton:hover { background-color: rgba(34, 34, 34, 0.8); border: 1px solid #e66b2c; }
        """)
        
        # Normal click opens the file
        card.clicked.connect(lambda: self.open_project_requested.emit(file_path))
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        thumb = QLabel()
        thumb.setFixedHeight(90)
        thumb.setStyleSheet("background-color: #111111; border-top-left-radius: 11px; border-top-right-radius: 11px; border-bottom: 1px solid rgba(255,255,255,0.05);")
        thumb.setPixmap(qta.icon('mdi6.movie-roll', color='#333333').pixmap(32, 32))
        thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(thumb)
        
        info_widget = QWidget()
        info_widget.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(10, 10, 10, 10)
        
        # Add Rename and Delete row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_lbl = QLabel(name)
        title_lbl.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold;")
        
        btn_rename = QPushButton(qta.icon('mdi6.pencil-outline', color='#808080'), "")
        btn_rename.setFixedSize(18, 18)
        btn_rename.setCursor(Qt.PointingHandCursor)
        btn_rename.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); border-radius: 4px; }")
        btn_rename.clicked.connect(lambda checked=False, p=file_path, n=name: self._handle_rename(p, n))
        
        btn_delete = QPushButton(qta.icon('mdi6.trash-can-outline', color='#808080'), "")
        btn_delete.setFixedSize(18, 18)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(255, 59, 48, 0.8); color: white; border-radius: 4px; }")
        btn_delete.clicked.connect(lambda checked=False, p=file_path: self._handle_delete(p))
        
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(btn_rename)
        title_row.addWidget(btn_delete)
        
        bottom_row = QHBoxLayout()
        date_lbl = QLabel(date)
        date_lbl.setStyleSheet("color: #808080; font-size: 10px;")
        dur_lbl = QLabel(duration)
        dur_lbl.setStyleSheet("color: #808080; font-size: 10px; font-family: monospace;")
        
        bottom_row.addWidget(date_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(dur_lbl)
        
        info_layout.addLayout(title_row)
        info_layout.addLayout(bottom_row)
        
        layout.addWidget(info_widget)
        return card

    def _create_trash_card(self, name, days_left, file_path):
        card = QFrame()
        card.setFixedSize(210, 160)
        card.setStyleSheet("""
            QFrame { background-color: rgba(26, 26, 26, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; }
            QFrame:hover { background-color: rgba(34, 34, 34, 0.8); border: 1px solid #ff3b30; }
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        thumb = QLabel()
        thumb.setFixedHeight(90)
        thumb.setStyleSheet("background-color: #111111; border-top-left-radius: 11px; border-top-right-radius: 11px; border-bottom: 1px solid rgba(255,255,255,0.05);")
        thumb.setPixmap(qta.icon('mdi6.delete-restore', color='#ff3b30').pixmap(32, 32))
        thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(thumb)
        
        info_widget = QWidget()
        info_widget.setStyleSheet("background: transparent; border: none;")
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(10, 10, 10, 10)
        
        title_lbl = QLabel(name)
        title_lbl.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold;")
        
        bottom_row = QHBoxLayout()
        date_lbl = QLabel(f"Expires in {days_left} days")
        date_lbl.setStyleSheet("color: #ff3b30; font-size: 10px; font-weight: bold;")
        
        btn_recover = QPushButton(qta.icon('mdi6.restore', color='#4CAF50'), "")
        btn_recover.setFixedSize(22, 22)
        btn_recover.setCursor(Qt.PointingHandCursor)
        btn_recover.setToolTip("Recover Project")
        btn_recover.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(76, 175, 80, 0.2); border-radius: 4px; }")
        btn_recover.clicked.connect(lambda _, p=file_path: self._handle_recover(p))
        
        btn_delete = QPushButton(qta.icon('mdi6.delete-forever', color='#ff3b30'), "")
        btn_delete.setFixedSize(22, 22)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setToolTip("Delete Permanently")
        btn_delete.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(255, 59, 48, 0.2); border-radius: 4px; }")
        btn_delete.clicked.connect(lambda _, p=file_path: self._handle_perm_delete(p))
        
        bottom_row.addWidget(date_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(btn_recover)
        bottom_row.addWidget(btn_delete)
        
        info_layout.addWidget(title_lbl)
        info_layout.addLayout(bottom_row)
        
        layout.addWidget(info_widget)
        return card

    def _handle_rename(self, file_path, current_name):
        """Displays a popup to get a new name, then updates everything."""
        new_name, ok = QInputDialog.getText(
            self, "Rename Project", "Enter new project name:", 
            text=current_name
        )
        if ok and new_name and new_name != current_name:
            success = project_manager.rename_project(file_path, new_name)
            if success:
                self.refresh_recent_projects()
            else:
                QMessageBox.warning(self, "Rename Failed", "Could not rename project. A file with this name might already exist or the file is locked.")

    def _handle_delete(self, file_path):
        """Soft deletes the project, moving it to the bin."""
        reply = QMessageBox.question(
            self, "Delete Project",
            "Are you sure you want to move this project to the trash?\n\nIt will be permanently deleted after 7 days.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if project_manager.soft_delete_project(file_path):
                self.refresh_recent_projects()
            else:
                QMessageBox.warning(self, "Delete Failed", "Could not delete project. Ensure the file is not locked.")

    def _handle_recover(self, file_path):
        if project_manager.recover_project(file_path):
            self.refresh_trash()
            
    def _handle_perm_delete(self, file_path):
        reply = QMessageBox.question(
            self, "Delete Permanently",
            "Are you sure you want to permanently delete this project? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if project_manager.permanent_delete(file_path):
                self.refresh_trash()

    def showEvent(self, event):
        """Every time the hub is shown, refresh the list."""
        super().showEvent(event)
        self.switch_page(self.content_stack.currentIndex())