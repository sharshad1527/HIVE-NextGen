import sys
import os
import numpy as np
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PySide6.QtCore import QTimer, Qt
from ui.viewport import HiveViewport
from core.logger import logger_manager, hive_logger

class ViewportTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HIVE Viewport Stability Test")
        self.resize(1280, 720)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        print("Initializing HiveViewport...")
        self.viewport = HiveViewport()
        layout.addWidget(self.viewport)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.generate_frame)
        self.timer.start(16) # ~60 FPS
        
        self.frame_count = 0
        
    def generate_frame(self):
        # Create a 1280x720 RGBA frame with a moving pattern
        w, h = 1280, 720
        frame = np.zeros((h, w, 4), dtype=np.uint8)
        
        # Moving vertical bar
        bar_pos = (self.frame_count * 5) % w
        frame[:, bar_pos:bar_pos+50, 0] = 255 # Red
        frame[:, bar_pos:bar_pos+50, 3] = 255 # Alpha
        
        # Static background pattern
        frame[::20, :, 1] = 100 # Green grid
        frame[::20, :, 3] = 255
        frame[:, ::20, 2] = 100 # Blue grid
        frame[:, ::20, 3] = 255
        
        self.viewport.update_frame((float(self.frame_count), frame))
        self.frame_count += 1
        if self.frame_count % 60 == 0:
            print(f"Rendered {self.frame_count} frames...")

def run_test():
    # Setup logging to console
    logs_dir = Path("HIVE-NextGen/logs")
    logger_manager.setup(logs_dir, verbose=True)
    hive_logger.info("Starting Viewport Stability Test...")

    app = QApplication(sys.argv)
    window = ViewportTestWindow()
    window.show()
    
    # Run for 10 seconds to verify stability
    QTimer.singleShot(10000, app.quit)
    
    print("Test running for 10 seconds. Check if you see a moving red bar on a grid.")
    app.exec()
    
    print("Test finished. Cleaning up...")
    window.viewport.cleanupGL()

if __name__ == "__main__":
    run_test()
