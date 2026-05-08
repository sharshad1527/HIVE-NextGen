# Phase 3.3: Master Shaders & Composition

## Objective
Implement multi-pass effect composition using FBOs and port core visual effects to the Master Shader.

## 🛠 Architectural Changes
1.  **FBO Compositing:** Use **Framebuffer Objects (FBOs)** to handle multi-pass rendering (e.g., render video -> apply blur -> composite).
2.  **Master Effect Shader:** Implementation of the "Uber Shader" handling Blur, Glow, VHS, Color Grading, and Glitch.
3.  **LRU Texture Cache:** Integrate a GPU-side cache to store frequently scrubbed textures.

## ✅ Implementation Steps

### 3.1 Multi-Pass FBO Pipeline
- Implement `FBOStack` in `ui/viewport.py`.
- Support for "Ping-Pong" rendering (necessary for separable Gaussian blurs).
- **Verification:** Render a video frame, blur it in one pass, and verify the output.

### 3.2 Porting Effects to GLSL
- Implement core logic in `core/shaders/master_effect.glsl`:
    - **Blur:** Multi-tap kernel.
    - **VHS:** Chromatic aberration + Scanlines + Jitter.
    - **Glow:** Threshold filter + Additive blend.
    - **Color Grading:** Saturation/Brightness/Contrast/Gamma.
- **Verification:** Compare GLSL output vs existing CV2 output for identical parameters.

### 3.3 Composition Logic
- Implement the "Layer Descriptor" system where `RenderEngine` sends a list of layers.
- Viewport iterates through layers, binding correct textures and uniforms.
- **Verification:** Render a scene with 2 video clips and 3 simultaneous effects without FPS drop.

## 🧪 Testing Protocol
- **A/B Test:** `tests/test_fx_accuracy.py` - Automated pixel comparison between old CV2 and new GLSL effects.
- **Stress Test:** Apply all effects at max intensity and measure GPU utilization.

## 🤖 Agent Instructions
- **THINKING & CODING:** Use **PRO MODEL**.
- **SIMPLE TASKS:** Use Flash/Lite.
- **DEBUGGING:** Log the number of FBO swaps and active texture units per frame to `hive_logger`.
