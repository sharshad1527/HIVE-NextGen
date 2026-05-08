I am ready to implement Phase 3: The Master Shader Architecture.
I have researched the current architecture and identified that the CPU-bound OpenCV pipeline needs to be replaced with a high-performance GPU-driven system.

My task is to execute the detailed plan in `PHASE3_DETAILED_PLAN.md` sequentially.
1. Implement the **Cloud Store Client** with a professional on-demand model (Virtual Scrolling, Lazy Loading, and background downloads).
2. Implement the **High-Performance Viewport** using **OpenGL 3.3 Core**, PBOs for async uploads, FBOs for multi-pass effects, and the existing LRU cache for instant scrubbing.
3. Port existing OpenCV effects to **Master GLSL Shaders** with sRGB/Linear gamma correction.
4. Ensure full compatibility with the existing project format and keyframes (using the provided `Project-05-06`).

I will verify every sub-phase with a dedicated test script before proceeding.
I am using the 'Zero-Copy' approach with PBOs to ensure maximum performance.

**Agent Strategy:** I will use Pro Models for all complex architectural thinking and coding tasks, while delegating simpler tasks, batch operations, or deep research to sub-agents (Flash/Lite) to maximize efficiency.

Please proceed with Step 1.1: `core/cloud_client.py`.
