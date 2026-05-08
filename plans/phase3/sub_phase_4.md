# Phase 3.4: Transitions & Hybrid Captions

## Objective
Finalize the GPU pipeline by implementing transitions and high-quality caption rendering.

## 🛠 Architectural Changes
1.  **Master Transition Shader:** Handles visual blending between two video textures based on a `progress` uniform.
2.  **Hybrid Captions:** Use `QPainter` to render text to a transparent texture, then animate it in GLSL.
3.  **Color Space Mastery:** Final sRGB/Linear gamma correction across the entire pipeline.

## ✅ Implementation Steps

### 4.1 Master Transition Shader
- Create `core/shaders/master_transition.glsl`.
- Implement:
    - **Cross Dissolve.**
    - **Slide / Wipe.**
    - **Glitch / Zoom transitions.**
- **Verification:** Test script to blend two textures from 0.0 to 1.0.

### 4.2 Hybrid Caption Rendering
- Refactor `RenderEngine._draw_caption` to output a `QImage`.
- Upload this `QImage` to the viewport as a separate texture layer.
- Apply GLSL animations (Typewriter reveal, Glow) to the caption texture.
- **Verification:** Add a caption to `Project-05-08` and verify smooth animation.

### 4.3 Final Polishing & Gamma
- Implement the shared `gamma_correct.glsl` include.
- Apply to the final output pass in the viewport.
- **Verification:** Visual check for black levels and color saturation against professional reference footage.

## 🧪 Testing Protocol
- **End-to-End Test:** `tests/test_full_render.py` - Render a 10-second sequence with multiple clips, transitions, and effects.
- **Project Compatibility:** Open and play `Project-05-06` without any modifications required to the `.hive` file.

## 🤖 Agent Instructions
- **THINKING & CODING:** Use **PRO MODEL**.
- **SIMPLE TASKS:** Use Flash/Lite.
- **DEBUGGING:** Log the final composition time (ms) and peak memory usage to `hive_logger`.
