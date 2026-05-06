# main.py
import sys
import os
import ctypes
import random
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QWidget, 
    QVBoxLayout, QProgressBar, QLabel
)
from PySide6.QtGui import (
    QIcon, QPainter, QRadialGradient, QColor, 
    QImage, QPixmap, QFont, QPainterPath, QPen
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize

from ui.main_window import MainWindow
from ui.project_hub import ProjectHubWindow
from core.project_manager import project_manager
from core.app_config import app_config
from core.font_manager import font_manager
from core.media_manager import media_manager
from core.logger import logger_manager
from utils.paths import get_asset_path

class StartupWorker(QThread):
    """
    Background worker that executes heavy initialization tasks to keep 
    the boot sequence responsive and the splash screen fluid.
"""
    progress_update = Signal(int, str)
    finished_successfully = Signal()

    def run(self):
        try:
            # 1. Cleanup temporary project cache / bin
            self.progress_update.emit(10, "Clearing temporary caches...")
            app_config.cleanup_bin()
            
            # 2. Initialize font engine and register custom fonts
            self.progress_update.emit(40, "Loading typography engine...")
            font_manager._ensure_initialized()
            
            # 3. Probe hardware for FFmpeg acceleration (OpenCV/FFmpeg)
            self.progress_update.emit(70, "Probing hardware acceleration...")
            media_manager.probe_hardware()
            
            # 4. Final handoff
            self.progress_update.emit(95, "Syncing system components...")
            self.msleep(500) # Ensure the user sees the final state
            
            self.progress_update.emit(100, "Ready.")
            self.finished_successfully.emit()
            
        except Exception as e:
            print(f"Startup Critical Error: {e}")
            self.progress_update.emit(100, "Initialization failed. Starting in safe mode...")
            self.finished_successfully.emit()

class SplashWindow(QWidget):
    """
    Frameless, premium splash screen for H.I.V.E NextGen.
    Features the signature dark metallic radial gradient and noise texture.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 320)
        
        self.bg_texture = None
        self._generate_premium_background_texture()
        
        self.setup_ui()
        self.center_on_screen()

    def _generate_premium_background_texture(self):
        """Generates the signature grain/noise texture to match the H.I.V.E aesthetic."""
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

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(10)
        
        # Branding: Logo
        self.logo_label = QLabel()
        logo_path = get_asset_path("logos", "HIVE_Logo_Mark.svg")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path).scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_label)
        
        # Branding: Title
        self.title_label = QLabel("H.I.V.E")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #e66b2c;
                font-size: 34px;
                font-weight: 900;
                font-style: italic;
                letter-spacing: 4px;
            }
        """)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Progress Feedback
        self.status_label = QLabel("INITIALIZING H.I.V.E ENGINE...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #808080;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #121212;
                border: none;
                border-radius: 1px;
            }
            QProgressBar::chunk {
                background-color: #e66b2c;
            }
        """)
        layout.addWidget(self.progress_bar)

    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message.upper())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect().adjusted(1, 1, -1, -1)
        
        # 1. Metallic Radial Gradient Background
        center = rect.center()
        gradient = QRadialGradient(center, rect.width() / 1.1)
        gradient.setColorAt(0.0, QColor(32, 32, 35))
        gradient.setColorAt(0.7, QColor(10, 10, 12))
        gradient.setColorAt(1.0, QColor(0, 0, 0))
        
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(230, 107, 44, 60), 1))
        painter.drawRoundedRect(rect, 15, 15)
        
        # 2. Grainy Texture Overlay
        if self.bg_texture:
            path = QPainterPath()
            path.addRoundedRect(rect, 15, 15)
            painter.setClipPath(path)
            painter.setOpacity(0.6)
            painter.drawTiledPixmap(rect, self.bg_texture)

    def center_on_screen(self):
        screen_geo = QApplication.primaryScreen().geometry()
        self.move(
            (screen_geo.width() - self.width()) // 2,
            (screen_geo.height() - self.height()) // 2
        )

class AppController:
    def __init__(self):
        if os.name == "nt":
            myappid = "harshad.hivenextgen"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("H.I.V.E NextGen")
        
        icon_path = get_asset_path("logos", "HIVE_App_Icon.ico") if os.name == "nt" else get_asset_path("logos", "HIVE_App_Icon.svg")
        self.app.setWindowIcon(QIcon(icon_path))
        self.app.setQuitOnLastWindowClosed(False)
        
        self.load_stylesheet()

        # Phase 1: Logging
        log_level = app_config.get_setting("logging_level", "INFO")
        is_verbose = "--verbose" in sys.argv or log_level == "DEBUG"
        logger_manager.setup(app_config.logs_dir, verbose=is_verbose)

        # Phase 2: Orchestration
        self.splash = SplashWindow()
        self.worker = StartupWorker()
        
        # Connect background worker to Splash
        self.worker.progress_update.connect(self.splash.update_progress)
        self.worker.finished_successfully.connect(self.on_startup_finished)
        
        # Windows (Initialized late to prevent blocking)
        self.hub = None
        self.editor = None

    def load_stylesheet(self):
        """Loads the custom QSS theme file globally"""
        style_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.app.setStyleSheet(f.read())

    def on_startup_finished(self):
        """Callback for when the background thread completes initialization."""
        self.hub = ProjectHubWindow()
        
        # Connect Hub signals to File Explorer dialogs
        self.hub.create_project_requested.connect(self.handle_create_project)
        self.hub.open_project_requested.connect(self.handle_open_project)
        
        # Ensure quitting completely when the Hub is closed
        original_hub_close = self.hub.closeEvent
        def _on_hub_close(event):
            original_hub_close(event)
            self.app.quit()
        self.hub.closeEvent = _on_hub_close
        
        # Transitions
        self.splash.close()
        self.hub.refresh_recent_projects()
        self.hub.show()

    def handle_create_project(self, project_type):
        """Automatically establishes the new project folder and file."""
        base_dir = app_config.default_project_path
        os.makedirs(base_dir, exist_ok=True)
        
        date_str = datetime.now().strftime("%m-%d")
        base_name = f"Project-{date_str}"
        project_name = base_name
        
        project_folder = os.path.join(base_dir, project_name)
        file_path = os.path.join(project_folder, f"{project_name}.hive")
        
        counter = 2
        while os.path.exists(project_folder) or os.path.exists(file_path):
            project_name = f"{base_name}({counter})"
            project_folder = os.path.join(base_dir, project_name)
            file_path = os.path.join(project_folder, f"{project_name}.hive")
            counter += 1
            
        os.makedirs(project_folder, exist_ok=True)
        project_manager.create_new_project(name=project_name, project_type=project_type)
        project_manager.save_project(file_path)
        
        self.launch_editor()

    def handle_open_project(self, file_path=""):
        """Opens a specific project, or asks the user to pick one if empty."""
        if not file_path:
            default_dir = os.path.expanduser("~/Documents")
            if not os.path.exists(default_dir):
                default_dir = os.path.expanduser("~")
                
            file_path, _ = QFileDialog.getOpenFileName(
                self.hub,
                "Open Hive Project",
                default_dir,
                "Hive Project Files (*.hive)"
            )
            
        if file_path and os.path.exists(file_path):
            success = project_manager.load_project(file_path)
            if success:
                self.launch_editor()
            else:
                QMessageBox.critical(self.hub, "Error", f"Could not read the project file:\n{file_path}")

    def launch_editor(self):
        """Hides the Hub and opens the Main Editor."""
        self.hub.hide()
        
        if not self.editor:
            self.editor = MainWindow()
            original_editor_close = self.editor.closeEvent
            def _on_editor_close(event):
                original_editor_close(event)
                self.show_hub()
            self.editor.closeEvent = _on_editor_close
            
        self.editor.showMaximized()

    def show_hub(self):
        """Returns to the Hub when the editor is closed."""
        self.editor = None 
        self.hub.refresh_recent_projects()
        self.hub.show()

    def run(self):
        """Starts the application with the splash screen."""
        self.splash.show()
        self.worker.start()
        sys.exit(self.app.exec())

if __name__ == "__main__":
    controller = AppController()
    controller.run()
