import sys
import os
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QSurfaceFormat
from core.shader_manager import get_shader_manager
from core.logger import hive_logger

class TestGLWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        # Set OpenGL 3.3 Core profile
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        self.setFormat(fmt)

    def initializeGL(self):
        self.sm = get_shader_manager()
        shader_path = Path("HIVE-NextGen/core/shaders/master_effect.glsl")
        
        print(f"Loading shader: {shader_path}")
        success = self.sm.load_program("master", str(shader_path))
        if success:
            print("Shader loaded successfully!")
        else:
            print("Shader loading failed!")
            sys.exit(1)

        self.sm.shader_reloaded.connect(self.on_reloaded)

    def on_reloaded(self, name):
        print(f"Shader '{name}' reloaded!")

def test_shader_hot_reload():
    app = QApplication(sys.argv)
    
    widget = TestGLWidget()
    widget.show()
    
    # Process events to allow initialization
    app.processEvents()
    
    shader_path = Path("HIVE-NextGen/core/shaders/master_effect.glsl")
    original_content = shader_path.read_text()
    
    try:
        print("Waiting for 2 seconds before modifying shader...")
        time.sleep(2)
        
        # Modify the shader
        new_content = original_content.replace("texColor.a * opacity", "texColor.a * opacity * 0.5")
        print("Modifying shader file...")
        shader_path.write_text(new_content)
        
        # Wait for watcher to trigger and reload
        print("Waiting for reload...")
        for _ in range(20): # Wait up to 2 seconds
            app.processEvents()
            time.sleep(0.1)
            
    finally:
        # Restore original content
        print("Restoring original shader content...")
        shader_path.write_text(original_content)
        
    print("Test finished.")
    # app.exec() # Don't block if running as a script

if __name__ == "__main__":
    test_shader_hot_reload()
