# START PROMPT: PHASE 4.2 & 4.3 - Backend Registry & Wiring

**System Mandate:** You are a Senior Backend and Graphics Pipeline Engineer. You MUST use the **PRO MODEL** for all architectural thinking, memory management strategies, and GPU wiring. Use Flash/Lite models ONLY for simple boilerplate.

## 🎯 Task: Implement Phase 4.2 & 4.3 Plan
You are tasked with building the data registry, lazy-loading memory manager, and the live UI-to-GPU bridge to power the Store Effects system.

**Read the full plan here first:** `plans/PHASE4_2_3_DETAILED_PLAN.md`

## 🏗 Execution Protocol

1. **Initial Mapping (Delegate to Sub-Agents):**
   - DO NOT fill your main context window with raw file reads.
   - Use your `codebase_investigator` sub-agent to map:
       - The `.hive` project saving/loading logic (`core/project_manager.py` or similar).
       - The existing caching logic (`core/frame_cache.py`).
       - The UI-to-Engine communication layer (`core/signal_hub.py` or similar).
   - Output the map to a temporary file (`temp_backend_map.md`) and review it.

2. **Draft Implementation Plan (TODO):**
   - Create a strict, step-by-step TODO plan.
   - Sequence it logically: First the Data Registry (4.2), then the `.hive` file integration, then the LRU Memory Management, and finally the UI-to-GPU Wiring (4.3).
   - Print this step-by-step plan in the chat for review.

3. **Development Guidelines:**
   - **Lazy Loading is Law:** The engine must only load assets when the playhead approaches them or the user explicitly clicks on them.
   - **Viewport Performance:** Implement dynamic resolution scaling for the viewport if render times exceed 16ms per frame. Smooth playback is priority #1.
   - **Logging:** Log cache hits/misses, GPU uniform injections, and RAM allocation limits clearly via `hive_logger`.

4. **Automated Testing & Self-Healing:**
   - **Mandatory Tests:** Create deep-logic tests for the Registry and Wiring (e.g., `tests/test_effect_registry.py`, `tests/test_gpu_wiring_latency.py`).
   - **Manual Run & Verification:** Execute the project-specific build and test commands (e.g., `pytest`, `ruff check`) autonomously.
   - **Error Handling:** If an error occurs:
     - Delegate deep debugging to a sub-agent.
     - Review the sub-agent's fix and apply it.
     - Re-validate with original and new test cases.
   - **Final Handshake:** You must confirm that `Project-05-06` loads and plays perfectly with the new backend before finishing.

5. **Action:**
   - Acknowledge these instructions and begin Step 1 immediately.
