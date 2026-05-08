import numpy as np
import ctypes
import threading
import OpenGL
# CRITICAL: Disable error checking to bypass Intel driver context detection bugs
OpenGL.ERROR_CHECKING = False
from OpenGL.GL import *
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QSurfaceFormat, QMatrix4x4
from PySide6.QtCore import Qt, Signal, QTimer
from core.shader_manager import get_shader_manager
from core.logger import hive_logger

class HiveViewport(QOpenGLWidget):
    """
    High-performance OpenGL 3.3 Core Viewport.
    Uses PBOs for async texture uploads from Numpy RGBA buffers.
    All GL operations are performed inside paintGL to ensure context stability.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set OpenGL 3.3 Core profile
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setAlphaBufferSize(8)
        fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
        self.setFormat(fmt)
        
        self.sm = None
        self.texture_id = 0
        self.vbo = 0
        self.vao = 0
        self.pbo_ids = []
        self.current_pbo_idx = 0
        self.num_pbos = 3 
        
        self.frame_width = 0
        self.frame_height = 0
        
        # Thread-safe frame storage
        self._next_frame = None
        self._frame_lock = threading.Lock()
        
        self.last_frame_time = 0.0 # Logical timestamp of the frame currently on the GPU
        
        self.initialized = False

    def initializeGL(self):
        """Setup OpenGL state, shaders, and buffers."""
        try:
            # Log GL Version/Vendor
            version = glGetString(GL_VERSION).decode()
            vendor = glGetString(GL_VENDOR).decode()
            hive_logger.info(f"HiveViewport: GL Initialized. Version: {version}, Vendor: {vendor}")
            
            self.sm = get_shader_manager()
            
            from pathlib import Path
            shader_path = Path(__file__).parent.parent / "core" / "shaders" / "master_effect.glsl"
            if not shader_path.exists():
                hive_logger.error(f"HiveViewport: Shader file NOT FOUND at {shader_path}")
                return
                
            if not self.sm.load_program("master", str(shader_path)):
                hive_logger.error("HiveViewport: Failed to load master shader!")
                return

            # Setup Quad Geometry
            vertices = np.array([
                -1.0,  1.0, 0.0,  0.0, 0.0,
                -1.0, -1.0, 0.0,  0.0, 1.0,
                 1.0, -1.0, 0.0,  1.0, 1.0,
                 
                -1.0,  1.0, 0.0,  0.0, 0.0,
                 1.0, -1.0, 0.0,  1.0, 1.0,
                 1.0,  1.0, 0.0,  1.0, 0.0 
            ], dtype=np.float32)

            self.vao = glGenVertexArrays(1)
            self.vbo = glGenBuffers(1)

            glBindVertexArray(self.vao)
            glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
            glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

            # Position attribute (index 0)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 5 * vertices.itemsize, ctypes.c_void_p(0))
            
            # TexCoord attribute (index 1)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 5 * vertices.itemsize, ctypes.c_void_p(3 * vertices.itemsize))

            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glBindVertexArray(0)

            # Setup PBOs
            self.pbo_ids = glGenBuffers(self.num_pbos)
            
            # Setup Texture
            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            
            # Pre-allocate a small initial texture to ensure it's valid
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, 2, 2, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
            glBindTexture(GL_TEXTURE_2D, 0)

            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            self.initialized = True
            hive_logger.info("HiveViewport: OpenGL initialized successfully.")
            self.update() # Trigger first repaint
        except Exception as e:
            hive_logger.error(f"HiveViewport: Critical Error in initializeGL: {e}")
            import traceback
            hive_logger.error(traceback.format_exc())

    def update_frame(self, data):
        """Thread-safe update of the next frame to be rendered. Accepts (logical_time, frame)."""
        if data is None:
            return
            
        with self._frame_lock:
            self._next_frame = data
        
        self.update()

    def _allocate_buffers(self, w, h):
        """Internal: Resize texture and PBOs. MUST be called with valid context."""
        hive_logger.info(f"HiveViewport: Allocating buffers for {w}x{h}")
        
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        
        data_size = w * h * 4
        for i, pbo_id in enumerate(self.pbo_ids):
            glBindBuffer(GL_PIXEL_UNPACK_BUFFER, pbo_id)
            glBufferData(GL_PIXEL_UNPACK_BUFFER, data_size, None, GL_STREAM_DRAW)
            hive_logger.debug(f"HiveViewport: PBO[{i}] (ID:{pbo_id}) allocated size: {data_size}")
        
        glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0)
        glBindTexture(GL_TEXTURE_2D, 0)

    def paintGL(self):
        if not self.initialized:
            return

        # 1. Process any pending frame updates (PBO Upload)
        frame_data = None
        with self._frame_lock:
            if self._next_frame is not None:
                frame_data = self._next_frame
                self._next_frame = None
                
        if frame_data is not None:
            try:
                logical_time, frame = frame_data
                self.last_frame_time = logical_time
                
                h, w = frame.shape[:2]
                
                # Re-allocate if resolution changed
                if w != self.frame_width or h != self.frame_height:
                    self.frame_width = w
                    self.frame_height = h
                    self._allocate_buffers(w, h)

                # Select PBOs
                self.current_pbo_idx = (self.current_pbo_idx + 1) % self.num_pbos
                pbo_id = self.pbo_ids[self.current_pbo_idx]
                ready_pbo_idx = (self.current_pbo_idx + 1) % self.num_pbos
                ready_pbo_id = self.pbo_ids[ready_pbo_idx]

                # A. Upload new frame to current PBO
                glBindBuffer(GL_PIXEL_UNPACK_BUFFER, pbo_id)
                glBufferSubData(GL_PIXEL_UNPACK_BUFFER, 0, frame.nbytes, frame)

                # B. Copy from the READY PBO to the texture
                glBindTexture(GL_TEXTURE_2D, self.texture_id)
                glBindBuffer(GL_PIXEL_UNPACK_BUFFER, ready_pbo_id)
                glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, ctypes.c_void_p(0))
                
                glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0)
                glBindTexture(GL_TEXTURE_2D, 0)
            except Exception as e:
                hive_logger.error(f"HiveViewport: Frame upload failed: {e}")

        # 2. Render Sequence
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)

        program = self.sm.get_program("master")
        if not program:
            return

        program.bind()
        
        # Bind VAO first for Core Profile compliance
        glBindVertexArray(self.vao)

        # Aspect Ratio Correction Matrix
        proj = QMatrix4x4()
        if self.frame_width > 0 and self.frame_height > 0:
            view_w, view_h = self.width(), self.height()
            aspect_view = view_w / view_h
            aspect_frame = self.frame_width / self.frame_height
            
            if aspect_view > aspect_frame:
                # Pillarbox (black bars on sides)
                scale_x = aspect_frame / aspect_view
                proj.scale(scale_x, 1.0, 1.0)
            else:
                # Letterbox (black bars top/bottom)
                scale_y = aspect_view / aspect_frame
                proj.scale(1.0, scale_y, 1.0)

        # Set Uniforms
        proj_loc = self.sm.get_uniform_location("master", "uProjection")
        program.setUniformValue(proj_loc, proj)

        opacity_loc = self.sm.get_uniform_location("master", "opacity")
        program.setUniformValue(opacity_loc, 1.0)
        
        tex_loc = self.sm.get_uniform_location("master", "screenTexture")
        program.setUniformValue(tex_loc, 0)

        # Bind Texture
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)

        # Draw
        glDrawArrays(GL_TRIANGLES, 0, 6)
        
        # Cleanup state
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, self.texture_id) # Unbind but stay on correct unit
        program.release()

    def resizeGL(self, w, h):
        if self.initialized:
            glViewport(0, 0, w, h)
            self.update() # Force refresh on resize

    def cleanupGL(self):
        """Releases GL resources on project close or destruction."""
        if not self.initialized:
            return
            
        self.makeCurrent()
        try:
            if self.texture_id: glDeleteTextures([self.texture_id])
            if self.vbo: glDeleteBuffers(1, [self.vbo])
            if self.vao: glDeleteVertexArrays(1, [self.vao])
            if len(self.pbo_ids) > 0: glDeleteBuffers(len(self.pbo_ids), self.pbo_ids)
        except Exception as e:
            hive_logger.error(f"HiveViewport: Cleanup failed: {e}")
        self.doneCurrent()
