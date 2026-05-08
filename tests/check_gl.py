import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtOpenGL import QOpenGLFunctions_3_3_Core
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QSurfaceFormat

def check_gl_signatures():
    app = QApplication(sys.argv)
    widget = QOpenGLWidget()
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    widget.setFormat(fmt)
    widget.show()
    
    # We need a context to initialize functions
    widget.makeCurrent()
    gl = QOpenGLFunctions_3_3_Core()
    gl.initializeOpenGLFunctions()
    
    print(f"GL Version: {gl.glGetString(gl.GL_VERSION)}")
    
    try:
        vaos = gl.glGenVertexArrays(1)
        print(f"glGenVertexArrays(1) type: {type(vaos)}, value: {vaos}")
    except Exception as e:
        print(f"glGenVertexArrays(1) failed: {e}")
        
    try:
        textures = gl.glGenTextures(1)
        print(f"glGenTextures(1) type: {type(textures)}, value: {textures}")
    except Exception as e:
        print(f"glGenTextures(1) failed: {e}")

    app.quit()

if __name__ == "__main__":
    check_gl_signatures()
