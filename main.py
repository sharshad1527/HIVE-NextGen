# main.py
import sys
import os

# SILENCE OPENCV POPUPS: Prefer FFmpeg/DirectShow over MSMF which spawns windows
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
os.environ["OPENCV_FFMPEG_THREADS"] = "1"

# FORCE OPENGL FOR QT QUICK TO AVOID D3D11 INCOMPATIBILITY WITH QOpenGLWidget
os.environ["QSG_RHI_BACKEND"] = "opengl"
os.environ["QT_QUICK_BACKEND"] = "opengl"

import ctypes
import random
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QWidget, 
    QVBoxLayout, QHBoxLayout, QProgressBar, QLabel
)
from PySide6.QtGui import (
    QIcon, QPainter, QRadialGradient, QColor, 
    QImage, QPixmap, QFont, QPainterPath, QPen
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize

# Core imports (Lightweight)
from core.project_manager import project_manager
from core.app_config import app_config
from core.font_manager import font_manager
from core.media_manager import media_manager
from core.logger import logger_manager
from utils.paths import get_asset_path
from ui.logo_animation import HiveLogoAnimation

class StartupWorker(QThread):
    """
    Background worker that executes heavy initialization tasks to keep 
    the boot sequence responsive and the splash screen fluid.
    """
    progress_update = Signal(int, str)
    finished_successfully = Signal()

    def run(self):
        try:
            # 1. Initialize core config and directories
            self.progress_update.emit(5, "Loading system configuration...")
            app_config.initialize()
            
            # 2. Setup Logging (now that logs_dir is guaranteed by app_config.initialize)
            log_level = app_config.get_setting("logging_level", "INFO")
            is_verbose = "--verbose" in sys.argv or log_level == "DEBUG"
            logger_manager.setup(app_config.logs_dir, verbose=is_verbose)
            
            # 3. Initialize font engine and register custom fonts
            self.progress_update.emit(25, "Loading typography engine...")
            font_manager._ensure_initialized()
            
            # 4. Probe hardware for FFmpeg acceleration (OpenCV/FFmpeg)
            self.progress_update.emit(45, "Probing hardware acceleration...")
            media_manager.probe_hardware()
            
            # 5. Pre-cache effects and transitions
            self.progress_update.emit(65, "Caching visual presets...")
            from core import preset_loader
            preset_loader.reload_all()
            
            # 6. MODULE PRE-WARMING: Import heavy UI modules in background
            # This populates sys.modules cache without blocking the main thread.
            modules_to_load = [
                ("ui.main_window", 82), ("ui.project_hub", 84), ("ui.player", 86),
                ("ui.timeline", 88), ("ui.workspace", 90), ("ui.properties", 92),
                ("core.audio_mixer", 94), ("core.video_decoder", 96), ("core.render_engine", 98)
            ]
            
            for mod_name, progress in modules_to_load:
                self.progress_update.emit(progress, f"Pre-warming {mod_name}...")
                __import__(mod_name)
            
            # 7. Final handoff
            self.progress_update.emit(100, "Ready.")
            self.finished_successfully.emit()
            
        except Exception as e:
            print(f"Startup Critical Error: {e}")
            import traceback
            traceback.print_exc()
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
        """Generates the signature grain/noise texture with optimized batching."""
        size = 128
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        
        for y in range(size):
            for x in range(size):
                r = random.random()
                if r > 0.3:
                    intensity = int(r * 18)
                    if (x + y) % 4 == 0: intensity += 8
                    image.setPixelColor(x, y, QColor(0, 0, 0, intensity + 15))
                elif r > 0.95:
                    image.setPixelColor(x, y, QColor(255, 255, 255, random.randint(2, 6)))
        
        self.bg_texture = QPixmap.fromImage(image)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 40)
        layout.setSpacing(10)
        
        # Branding: Animated Logo
        self.logo_animation = HiveLogoAnimation()
        self.logo_animation.setFixedSize(240, 160)
        self.logo_animation.start_flow("A")
        layout.addWidget(self.logo_animation, alignment=Qt.AlignCenter)
        
        # Branding: Title
        self.title_label = QLabel("H.I.V.E")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #e66b2c;
                font-size: 34px;
                font-weight: 900;
                font-style: italic;
                letter-spacing: 4px;
                padding-left: 4px;
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
        self.app.setProperty("controller", self)
        
        icon_path = get_asset_path("logos", "HIVE_App_Icon.ico") if os.name == "nt" else get_asset_path("logos", "HIVE_App_Icon.svg")
        self.app.setWindowIcon(QIcon(icon_path))
        self.app.setQuitOnLastWindowClosed(False)
        
        self.load_stylesheet()

        # Phase 1: Orchestration
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
        # Late import: The code is already pre-warmed in the worker thread
        from ui.project_hub import ProjectHubWindow
        from core.audio_mixer import audio_mixer
        
        # Finalize hardware initialization on the main thread
        audio_mixer.initialize()
        
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
        
        # --- OS File Association / Command Line Launch ---
        target_project = None
        for arg in sys.argv[1:]:
            if arg.endswith(".hive"):
                target_project = arg
                break
            elif arg.endswith(".hivezip"):
                print(f"OS LAUNCH: Importing portable project {arg}...")
                target_project = project_manager.import_portable_project(arg, app_config.default_project_path)
                break
        
        if target_project and os.path.exists(target_project):
            if target_project.endswith(".hive"):
                # If it's a direct .hive, just highlight it in Hub first
                self.hub.show()
                self.hub.highlight_project(target_project)
                # Auto-open after a short delay so the user sees the glow
                QTimer.singleShot(1500, lambda p=target_project: self.handle_open_project(p))
            else:
                self.hub.show()
        else:
            self.hub.show()

    def handle_create_project(self, project_type):
        """Automatically establishes the new project folder and file."""
        # Save old project first if editor is active
        if self.editor:
            self.editor.save_current_project()

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
        
        # Reset Editor UI if it exists
        if self.editor:
            self.editor.panel_timeline.tracks_canvas.clear_all()
            self.editor.panel_player.update_duration(0.0)
            self.editor.panel_player.update_playhead(0.0)
            self.editor.panel_workspace.clear_media_bin()
        
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
                "Hive Project Files (*.hive *.hivezip)"
            )
            
        if file_path and os.path.exists(file_path):
            if file_path.endswith('.hivezip'):
                from core.app_config import app_config
                extract_root = str(app_config.default_project_path)
                hive_file = project_manager.import_portable_project(file_path, extract_root)
                if hive_file:
                    success = project_manager.load_project(hive_file)
                else:
                    success = False
            else:
                success = project_manager.load_project(file_path)
                
            if success:
                self.launch_editor()
            else:
                QMessageBox.critical(self.hub, "Error", f"Could not read the project file:\n{file_path}")

    def launch_editor(self):
        """Hides the Hub and opens the Main Editor."""
        self.hub.hide()
        
        if not self.editor:
            from ui.main_window import MainWindow
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
