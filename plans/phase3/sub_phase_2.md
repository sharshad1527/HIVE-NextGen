# Phase 3.2: Shader Manager & Viewport Core

## Objective
Establish the high-performance OpenGL foundation by implementing a central Shader Manager and a PBO-powered viewport.

## 🛠 Architectural Changes
1.  **Shader Manager (`core/shader_manager.py`):** Centralized registry for GLSL programs with support for shared `#include` files and hot-reloading.
2.  **Base Viewport (`ui/viewport.py`):** A `QOpenGLWidget` that replaces the drawing logic of `TimelinePreviewCanvas`.
3.  **Zero-Copy Async Uploads:** Use **Pixel Buffer Objects (PBOs)** to transfer Numpy RGBA frames from the `VideoDecoder` to GPU memory without blocking the UI thread.

## ✅ Implementation Steps

### 2.1 The Shader Manager
- Create `core/shader_manager.py`.
- Features:
    - Custom preprocessor to handle `#include "common.glsl"`.
    - Automatic recompilation when `.glsl` files are saved.
    - Caching of uniform locations for maximum performance.
- Create `core/shaders/master_effect.glsl` (Placeholder vertex and fragment shaders).
- **Verification:** Test script to load a shader, modify the file, and verify it reloads automatically.

### 2.2 The OpenGL Viewport
- Create `ui/viewport.py` inheriting from `QOpenGLWidget` and `QOpenGLFunctions_3_3_Core`.
- Implementation:
    - `initializeGL()`: Setup PBOs and textures.
    - `paintGL()`: Simple quad rendering with the current frame texture.
- **Verification:** Render a single static image using the new viewport.

### 2.3 PBO Integration
- Refactor `RenderEngine` to provide raw Numpy RGBA buffers.
- Implement the "Triple Buffer" PBO upload logic in `HiveViewport`.
- **Verification:** Run `Project-05-08` and verify video frames appear on the new viewport with 0% CPU conversion overhead.

## 🧪 Testing Protocol
- **Performance Test:** `tests/test_pbo_speed.py` - Compare `glTexSubImage2D` vs PBO upload times.
- **Regression Test:** Ensure interactive dragging/resizing handles (still rendered via `QPainter` on top) remain perfectly synced with the video frame.

## 🤖 Agent Instructions
- **THINKING & CODING:** Use **PRO MODEL**.
- **SIMPLE TASKS:** Use Flash/Lite.
- **DEBUGGING:** Log GL error codes (`glGetError`) and shader compilation logs to `hive_logger`.
