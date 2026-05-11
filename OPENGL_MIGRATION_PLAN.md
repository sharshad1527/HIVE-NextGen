# HIVE-NextGen: Master Bug List & OpenGL Migration Plan

*Generated: May 11, 2026*

This document outlines the architectural flaws, performance bottlenecks, and a step-by-step roadmap to complete the transition from the legacy OpenCV/QPainter pipeline to a professional, hardware-accelerated OpenGL pipeline.

---

## 🚨 Master Bug List

### 1. Rendering & GPU Upload (The Pipeline Choke)
*   **BUG-R1: CPU-Bound Composition** (`core/render_engine.py`): The `RenderEngine` uses `QPainter` on a `QImage` to composite layers, crop, and transform. This maxes out the CPU, capping framerates and defeating the purpose of hardware acceleration.
*   **BUG-R2: Redundant Memory Copies** (`core/render_engine.py`): Converting the composited `QImage` back to a Numpy array (`arr.copy()`) holds the Python GIL on massive memory blocks, stalling all other threads (specifically the video decoder).
*   **BUG-R3: UI Thread Blocking Uploads** (`ui/viewport.py`): Calling `glBufferSubData` to push 1080p/4K pixel arrays to the GPU happens synchronously on the main PySide6 UI thread. This causes the UI and timeline playhead to stutter every frame.

### 2. Media Decoding & Processing
*   **BUG-M1: CPU Color Space Conversion** (`core/video_decoder.py`): `PyAV` decodes YUV video, but the code forces it to convert to RGBA (`to_ndarray(format='rgba')`) and scale on the CPU before passing it to the engine.
*   **BUG-M2: Re-reading Static Images** (`core/render_engine.py`): Static images (e.g., PNGs) are loaded from the hard drive (`cv2.imread`) on *every single frame* they are rendered, instead of caching the pixel data into memory.
*   **BUG-M3: Thread-Unsafe OpenCV Seek/Read** (`core/media_manager.py`): Shared `cv2.VideoCapture` objects are used to seek and read frames across different threads without mutex locks, guaranteeing race conditions, deadlocks, and random crashes.
*   **BUG-M4: Main Thread Probing** (`ui/player.py`): Requesting metadata or clip screen bounds dynamically invokes OpenCV on the main UI thread, causing interface freezes.

### 3. Audio Stability
*   **BUG-A1: FFT Resampling in Real-Time Callback** (`core/audio_mixer.py`): Using `scipy.signal.resample` (Fourier Transform based) inside the `_audio_callback`. Real-time audio callbacks must complete in <1ms; FFTs cause massive CPU spikes, audio crackling, and engine stalls.
*   **BUG-A2: Blocking I/O in Callback** (`core/audio_mixer.py`): Reading audio files directly from disk (`read_chunk`) inside the real-time audio thread.

### 4. Timeline & UI Performance
*   **BUG-T1: O(N^2) Paint Event** (`ui/timeline/timeline_canvas.py`): The `paintEvent` (triggered on mouse movement) iterates inefficiently over all clips and triggers synchronous disk I/O and CPU-scaling for thumbnails.
*   **BUG-T2: FFmpeg Fork-Bombing** (`ui/timeline/timeline_canvas.py`): Generating dynamic thumbnails spawns synchronous `subprocess.Popen` FFmpeg calls. Zooming out on a complex timeline spawns dozens of processes simultaneously, potentially freezing the OS.

---

## 🗺️ Step-by-Step OpenGL Migration & Fix Plan

To transition the engine to a 15+ year NLE standard, implement these fixes in the following order.

### Phase 1: Decouple & Stabilize (The "Don't crash" phase)
1.  **Fix the Audio Mixer (BUG-A1, A2):** 
    *   Rip out `scipy.signal.resample`.
    *   Implement a fast linear interpolator or pre-resample audio tracks on import. 
    *   Load audio into a thread-safe ring buffer so the callback never touches the disk.
2.  **Lock the Media Manager (BUG-M3):** 
    *   Add a `threading.Lock()` around all OpenCV `set(CAP_PROP_POS_FRAMES)` and `read()` calls, or isolate `VideoCapture` objects per thread.
3.  **Cache Static Media (BUG-M2):** 
    *   Load images into memory *once* when added to the timeline, not every frame.

### Phase 2: The True OpenGL Pipeline (The "Fast" phase)
1.  **Stop CPU Compositing (BUG-R1):** 
    *   Rip `QPainter` out of `RenderEngine`. The RenderEngine should only orchestrate the timeline, identify active frames, and pass that list of raw frames to the Viewport.
2.  **Upload YUV Textures (BUG-M1):** 
    *   Change the `VideoDecoder` to output raw Y, U, and V numpy arrays (bypassing RGBA conversion).
3.  **Background Texture Upload (BUG-R3):** 
    *   Create an off-screen `QOpenGLContext` shared with the Viewport. Have the RenderEngine upload the YUV textures to the GPU on a background thread.
4.  **Shader Composition:** 
    *   Write a Fragment Shader (`master_effect.glsl`) that takes multiple texture inputs, performs YUV->RGB conversion natively in hardware, and handles all alpha blending, cropping, and positioning on the GPU.

### Phase 3: UI Optimization (The "Smooth" phase)
1.  **Thumbnail Caching (BUG-T1, T2):** 
    *   Implement a background worker thread that extracts thumbnails using a persistent FFmpeg/PyAV instance and saves them to a low-res image cache. 
    *   The `paintEvent` should only draw from this memory cache, never spawning subprocesses.
2.  **Pull-based Playback Sync:** 
    *   Instead of a `QTimer` pushing frames to the screen, sync playback to the Audio buffer's exact sample count, requesting frames from the RenderEngine only when the screen asks for a refresh.
