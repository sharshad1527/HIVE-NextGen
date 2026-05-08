# H.I.V.E NextGen: Phase 3 Master Implementation Plan

This is the master index for the GPU migration and Cloud Store integration. The implementation is split into four discrete, sequential sub-phases.

## 🗺 Phase 3 Roadmap

### 1. [Cloud Store & UI Virtualization](phase3/sub_phase_1.md)
- **Status:** Completed ✅
- **Goal:** On-demand fetching, conditional catalog updates, and high-performance UI list virtualization.
- **Start Prompt:** [START_PROMPT_PHASE_3_1.md](phase3/START_PROMPT_PHASE_3_1.md)

### 2. [Shader Manager & Viewport Core](phase3/sub_phase_2.md)
- **Status:** Ready 🚀
- **Goal:** OpenGL 3.3 Core foundation, PBO async uploads, and hot-reloading Shader Manager.
- **Start Prompt:** [START_PROMPT_PHASE_3_2.md](phase3/START_PROMPT_PHASE_3_2.md)

### 3. [Master Shaders & Composition](phase3/sub_phase_3.md)
- **Status:** Pending
- **Goal:** Multi-pass FBO rendering and porting effects (Blur, Glow, VHS) to GLSL.
- **Start Prompt:** [START_PROMPT_PHASE_3_3.md](phase3/START_PROMPT_PHASE_3_3.md)

### 4. [Transitions & Hybrid Captions](phase3/sub_phase_4.md)
- **Status:** Pending
- **Goal:** GLSL transitions, hybrid text rendering, and sRGB/Linear gamma correction.
- **Start Prompt:** [START_PROMPT_PHASE_3_4.md](phase3/START_PROMPT_PHASE_3_4.md)

---

## 🛠 Architectural Mandates (Apply to all Phases)
- **Model Usage:** 
    - **PRO MODEL** for all complex architectural thinking, logic, and coding.
    - **Flash/Lite Models** for boilerplate, research, and simple tool tasks.
- **Sub-Agents:** Use `codebase_investigator` for deep mapping and `generalist` for batch operations.
- **Logging:** Mandatory `hive_logger` debug logs for all new logic (Network, GL, Model updates).
- **Validation:** Every phase must be verified with a dedicated test script and manual playback using `Project-05-08`.
