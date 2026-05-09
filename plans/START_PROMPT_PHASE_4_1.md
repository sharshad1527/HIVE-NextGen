# START PROMPT: PHASE 4.1 - Visual Interaction & Store UI

**System Mandate:** You are a Senior UI/UX Desktop Application Developer operating as the orchestrator for this codebase. You MUST use the **PRO MODEL** for all architectural thinking, planning, and coding logic. Use Flash/Lite models ONLY for small, isolated sub-tasks.

## 🎯 Task: Implement Phase 4.1 Plan
You are tasked with implementing the UI/UX for the Effects, Captions, and Transitions store (CapCut-style grid, async downloads, timeline tracks, and contextual properties).

**Read the full plan here first:** `plans/PHASE4_1_DETAILED_PLAN.md`

## 🏗 Execution Protocol

1. **Initial Mapping (Delegate to Sub-Agents):**
   - DO NOT fill your main context window with raw file reads.
   - Use your `codebase_investigator` sub-agent to map the existing UI codebase (specifically `ui/sidebar.py`, `ui/timeline/`, `ui/properties.py`, `ui/preset_model.py`).
   - Instruct the sub-agent to output a comprehensive mapping of classes, signals, and integration points to a temporary markdown file (e.g., `temp_ui_map.md`). Read this file to build your mental model.

2. **Draft Implementation Plan (TODO):**
   - Based on the map, create a strict, step-by-step TODO plan outlining exactly which files will be modified and in what order. 
   - Print this step-by-step plan in the chat for review before you begin writing code.

3. **Development Guidelines:**
   - **Split Work:** Implement UI components one by one (e.g., first the Virtualized Grid, then the Async Download UX, then the Timeline Drops).
   - **Performance:** UI Thread MUST NEVER block. Use proper Qt asynchronous paradigms (QThread/Signals) for fetching, loading thumbnails, and animations.
   - **Logging & Debugging:** Log EVERYTHING. Use the internal logger to trace every UI state change, download trigger, and timeline drop event. If an error occurs, it must be completely traceable via the console.

4. **Automated Testing & Self-Healing:**
   - **Mandatory Tests:** For every component implemented, you MUST create a dedicated test script (e.g., `tests/test_ui_grid_virtualization.py`).
   - **Manual Run & Verification:** You must execute these tests yourself. Do not wait for the user to tell you.
   - **Error Handling:** If a test fails or a bug is found:
     - Use a sub-agent to analyze the logs and the failing code.
     - Automatically propose and apply the fix.
     - Re-run tests until 100% success is achieved.
   - **Zero-Error Policy:** You are responsible for confirming the implementation is error-free before declaring the phase complete.

5. **Action:**
   - Acknowledge these instructions and begin Step 1 immediately.
