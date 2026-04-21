# main.py
import sys
import os
import ctypes
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtGui import QIcon
from ui.main_window import MainWindow
from ui.project_hub import ProjectHubWindow
from core.project_manager import project_manager
from datetime import datetime
from core.app_config import app_config
from utils.paths import get_asset_path

class AppController:
    def __init__(self):
        if os.name == "nt":
            myappid="harshad.hivenextgen"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        self.app = QApplication(sys.argv)
        
        self.app.setApplicationName("H.I.V.E NextGen")
        if os.name == "nt":
            self.app.setWindowIcon(QIcon(get_asset_path("logos", "HIVE_App_Icon.ico")))
        else:
            self.app.setWindowIcon(QIcon(get_asset_path("logos", "HIVE_App_Icon.svg")))
        
        self.app.setQuitOnLastWindowClosed(False)  # Fix: Prevent Qt from tearing down objects when Editor closes
        self.load_stylesheet()

        # Initialize windows (Editor is None until needed)
        self.hub = ProjectHubWindow()
        self.editor = None
        
        # Fix: Ensure quitting completely when the Hub is closed
        original_hub_close = self.hub.closeEvent
        def _on_hub_close(event):
            original_hub_close(event)
            self.app.quit()
        self.hub.closeEvent = _on_hub_close
        
        # Connect Hub signals to File Explorer dialogs
        self.hub.create_project_requested.connect(self.handle_create_project)
        self.hub.open_project_requested.connect(self.handle_open_project)

    def load_stylesheet(self):
        """Loads the custom QSS theme file globally"""
        style_path = os.path.join(os.path.dirname(__file__), "styles", "theme.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.app.setStyleSheet(f.read())
        else:
            print(f"Warning: Stylesheet not found at {style_path}")

    def handle_create_project(self, project_type):
        """Automatically establishes the new project folder and file without a Save As dialog"""
        base_dir = app_config.default_project_path
        os.makedirs(base_dir, exist_ok=True)
        
        # Generate the dynamic name
        date_str = datetime.now().strftime("%m-%d")
        base_name = f"Project-{date_str}"
        project_name = base_name
        
        project_folder = os.path.join(base_dir, project_name)
        file_path = os.path.join(project_folder, f"{project_name}.hive")
        
        # Check if it exists and append counter if necessary
        counter = 2
        while os.path.exists(project_folder) or os.path.exists(file_path):
            project_name = f"{base_name}({counter})"
            project_folder = os.path.join(base_dir, project_name)
            file_path = os.path.join(project_folder, f"{project_name}.hive")
            counter += 1
            
        # Ensure project specific folder exists
        os.makedirs(project_folder, exist_ok=True)
            
        # Setup the Brain and Save immediately
        project_manager.create_new_project(name=project_name, project_type=project_type)
        project_manager.save_project(file_path)
        
        self.launch_editor()

    def handle_open_project(self, file_path=""):
        """Opens a specific project, or asks the user to pick one if empty"""
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
                QMessageBox.critical(self.hub, "Error", f"Could not read the project file:\n{file_path}\n\nIt might be corrupted or in an older format.")

    def launch_editor(self):
        """Hides the Hub and opens the Main Editor"""
        self.hub.hide()
        
        if not self.editor:
            self.editor = MainWindow()
            # Fix: Safely catch the editor closing to show the hub, instead of using 'destroyed'
            original_editor_close = self.editor.closeEvent
            def _on_editor_close(event):
                original_editor_close(event)
                self.show_hub()
            self.editor.closeEvent = _on_editor_close
            
        self.editor.showMaximized()

    def show_hub(self):
        """Returns to the Hub when the editor is closed"""
        self.editor = None # Clear memory
        self.hub.refresh_recent_projects() # Update list
        self.hub.show()

    def run(self):
        self.hub.show()
        sys.exit(self.app.exec())

if __name__ == "__main__":
    controller = AppController()
    controller.run()