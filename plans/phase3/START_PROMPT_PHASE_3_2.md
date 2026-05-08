I am ready to implement **Phase 3.2: Shader Manager & Viewport Core**.

I have read the plan in `plans/phase3/sub_phase_2.md`.
My goal is to implement the `ShaderManager` with hot-reloading and shared includes, and create the base `HiveViewport` with PBO-powered async texture uploads.

**Key Constraints:**
- **THINKING & CODING:** I will use the **PRO MODEL**.
- **SIMPLE TASKS:** I will use Flash/Lite models.
- **LOGGING:** I will log GL errors and shader compilation logs to `hive_logger`.
- **COMPATIBILITY:** I will ensure interactive handles remain synced with the new GL surface.

I will start by implementing the `ShaderManager` in `core/shader_manager.py`.

Please proceed.
