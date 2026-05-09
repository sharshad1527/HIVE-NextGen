# Phase 4.2 & 4.3: Backend Registry & GPU Wiring

## Objective
To implement the "Brain" (Phase 4.2) and the "Nervous System" (Phase 4.3) that powers the Phase 4.1 UI. This architecture prioritizes smooth playback, efficient memory management via lazy loading, and lightweight project files, mirroring the performance of professional tools like CapCut.

---

## Phase 4.2: The Registry & Data Management ("The Brain")

### 1. Lightweight Project Files
*   **Strategy:** "Save Links Only." The `.hive` project file will NOT bundle actual effect assets (JSONs, textures, fonts).
*   **Implementation:** The project file will save a reference (e.g., `store_id: "vhs_retro"`, `version: "1.2"`) and the user's custom settings (keyframe data, intensity).
*   **Project Loading:** When a project is opened, the Engine will parse these links and check the local `cloud_cache`. If an asset is missing (e.g., sent to a friend), it queues a background download.

### 2. Intelligent Catalog Caching
*   **Strategy:** Daily Catalog Sync.
*   **Implementation:** The `store_catalog.json` will only be fetched from the GitHub CDN once per day to prevent slow startups.
*   **Updates:** We will auto-update effects if a new catalog is pulled, but we will NOT block project loading to check for updates.
*   **Manual Refresh:** Add a "Force Refresh" option in the UI for immediate store updates.

### 3. The Central "Effect Registry"
*   Create a robust internal manager that maps UI interactions to local file paths. When the UI asks for `cross_dissolve`, the Registry instantly returns `cloud_cache/transitions/cross_dissolve.json`.

---

## Phase 4.3: Memory Management & GPU Wiring ("The Nervous System")

### 1. "CapCut-Style" Lazy Loading & LRU Cache
*   **Strategy:** Load strictly what is needed, when it's needed.
*   **Implementation:**
    *   **Proximity Loading:** Do not load all 50 effects at launch. As the playhead approaches an effect on the timeline, asynchronously load the required shaders and textures into the GPU.
    *   **Offloading:** Aggressively unload resources from the GPU that are far behind or far ahead of the playhead.
    *   **Priority Loading:** If a user clicks on an effect in the timeline (to view its properties), that effect gets top priority and is loaded immediately.
    *   **RAM Limits:** Utilize the existing LRU (Least Recently Used) cache logic to strictly enforce user-defined RAM limits.

### 2. Smooth Editing First (Performance Over Perfection)
*   **Strategy:** The viewport must never freeze.
*   **Implementation:**
    *   **Dynamic Resolution:** If the GPU struggles to render stacked effects in real-time, automatically drop the internal FBO rendering resolution (e.g., from 1080p to 720p or 540p) to maintain playback FPS.
    *   **Export Guarantee:** Ensure the "Export Engine" always renders at full quality, regardless of the viewport's proxy resolution.

### 3. The Live "Injection" Bridge
*   **Strategy:** Real-time property updates.
*   **Implementation:** Build the bridge between Phase 4.1 UI sliders and Phase 3 GLSL Uniforms. When a user moves an "Intensity" slider, the value is instantly injected into the active shader program without requiring a full frame reload.

## 🧪 Testing & Validation
*   **Unit Tests:** Validate the Registry's ability to map IDs to paths and handle missing assets.
*   **Performance Tests:** Measure the latency between a UI slider movement and the GPU uniform update (Target: <16ms).
*   **Project Stress Test:** Load a project with 100+ linked effects and verify smooth playback via the LRU cache.
*   **Self-Healing:** AI is mandated to autonomously debug and fix any memory leaks or logic errors using specialized sub-agents.
