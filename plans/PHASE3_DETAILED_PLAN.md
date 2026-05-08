# H.I.V.E NextGen: Phase 3 - Detailed Implementation Plan

## Objective
To replace the CPU-bound OpenCV rendering pipeline with a GPU-accelerated "Master Shader Architecture" and integrate the GitHub-based Cloud Store for on-demand preset delivery.

## Key Architectural Decisions
1.  **Shift to Viewport-Driven Rendering:** Instead of the `RenderEngine` thread generating a `QImage`, it will now produce a "Frame Descriptor" (RenderScene). The `QOpenGLWidget` (Viewport) will consume this descriptor and perform the actual GL draw calls.
2.  **Master Shaders (Uber Shaders):** Minimize state changes by using three powerful shaders (`effect`, `transition`, `caption`) that handle all visual variations via dynamic uniforms.
3.  **Zero-Copy Memory:** Decoded video frames (Numpy arrays) will be uploaded directly to GPU textures using `glTexSubImage2D` to avoid unnecessary buffer copies.
4.  **Hybrid Interaction:** Use `QPainter` on top of the `QOpenGLWidget` to render interactive handles, preserving existing clip manipulation logic.

---

## Sub-Phase 1: Cloud Store Client & Cache (Professional On-Demand System)

**Objective:** Implement a lightweight, high-performance "Store" interface that fetches presets on-demand, manages local caching, and handles thousands of items without UI lag.

### 1.1 The Cloud Client (`core/cloud_client.py`)
- **Catalog Management:** Fetches `store_catalog.json` once on startup and caches it. Provides a `force_refresh()` method triggered by the UI.
- **On-Demand Worker:** Uses `QThread` or `QRunnable` to download assets (JSONs + Thumbnails) in the background to prevent UI freezing.
- **Cache Registry:** Tracks which items are `Local`, `Cloud (Available)`, or `Downloading`.
- **Integrity Check:** Verifies checksums/file sizes before adding to the local preset registry.

### 1.2 The "Infinite" UI Tabs (`ui/sidebar_tabs.py`)
- **Model/View Architecture:** Replace static layouts with `QListView` and a custom `QAbstractListModel`. This enables **Virtual Scrolling** (only rendering what is visible), preventing lag even with 10,000+ presets.
- **Dynamic Thumbnails:** 
    - UI shows a "Loading" placeholder.
    - `ThumbnailManager` fetches generic base images from CDN in the background.
    - **Pro Feature:** Once downloaded, the UI can optionally overlay the preset's name or a "Preview" badge using `QPainter`.
- **Download States:** Each item displays a status icon:
    - `Cloud Icon`: Click to start download.
    - `Spinner`: Downloading...
    - `No Icon`: Locally ready to use.

### 1.3 The Preset Integration
- Once a download finishes, the `PresetLoader` is signaled to "Hot-Reload" the new JSON.
- The item in the UI instantly updates from "Downloadable" to "Applicable".
- **Category Filtering:** Use a `QSortFilterProxyModel` to allow users to filter by "Glitch", "Cinematic", "Modern", etc., without re-fetching the catalog.

---

## Technical Questions for Refinement
1. **Metadata:** Should we include the **estimated file size** in `store_catalog.json` to show a progress bar/size label during download? Yup.
2. **Preview Mode:** When a user clicks a "Cloud" preset (not yet downloaded), should it **auto-download and then apply** immediately, or just download to the library? Auto download, and add to library, and add a glow effect on it for few seconds so we can know thats the effect user downloaded. we dont apply it., just download it.
3. **Categorization:** Do you want the categories to be **hardcoded** (Effects, Transitions, Captions) or **dynamic** based on tags in the JSON (e.g., "Trending", "VHS", "Gaming")? Yup dynamic, and a hardcoded category named "My Presets" for locally downloaded presets., and favorite to save their favorite presets. And also search bar to search for presets.
4. **Storage:** Should we store cloud-downloaded presets in the standard `presets/` folder, or a separate `cloud_cache/` folder to distinguish "System Presets" from "Downloaded Store Content"? Yup separate.


---

## Sub-Phase 2: OpenGL Foundation (The High-Performance Viewport)

**Goal:** Create a robust, production-grade viewport that handles multi-layer composition, async uploads, and letterboxing.

### 2.1 The Master Shader Manager (`core/shader_manager.py`)
- **Singleton Shader Registry:** Manages the lifecycle of `QOpenGLShaderProgram` objects.
- **Shader Library:** Support for "Include" files (e.g., `common_math.glsl`) so that complex noise or color functions can be shared across Effect, Transition, and Caption shaders.
- **Uniform Caching:** Prevents redundant `glGetUniformLocation` calls every frame—critical for performance when thousands of parameters are moving.
- **Dev-Mode Hot-Reload:** Monitor `.glsl` files for changes and recompile them in real-time without restarting the app.

### 2.2 The Viewport Engine (`ui/viewport.py`)
- **Inheritance:** `HiveViewport(QOpenGLWidget, QOpenGLFunctions_4_1_Core)` (or highest supported version).
- **Asynchronous Uploads (PBOs):**
    - Instead of blocking the UI thread with `glTexSubImage2D`, use **Pixel Buffer Objects**. 
    - This allows the `RenderEngine` to dump Numpy data into a DMA (Direct Memory Access) buffer while the GPU continues rendering.
- **FBO Compositing (Offscreen Rendering):**
    - Use **Framebuffer Objects (FBOs)** for multi-pass effects.
    - Example: Render the video to `FBO_A` -> Apply Blur Pass to `FBO_B` -> Blend with original for a "Glow" effect.
- **Dynamic Letterboxing:**
    - Logic to calculate the "Inner Canvas" based on the project resolution (e.g., 9:16) while keeping the widget container responsive.
- **Texture Unit Manager:**
    - A dedicated manager to track which texture units (0, 1, 2...) are assigned to Video A, Video B, Mask, or Color LUTs.

### 2.3 Frame Synchronization
- Implement a **Triple-Buffer** approach:
    1. `RenderEngine` is writing to Buffer 1.
    2. Viewport is uploading Buffer 2.
    3. GPU is drawing from Buffer 3.
- This ensures 0% screen tearing and maximum 60fps fluidity.

---

## Finalized Architectural Decisions
1. **OpenGL Version:** **OpenGL 3.3 Core Profile**. Target cross-platform stability and maximum compatibility with older hardware.
2. **Caching Strategy:** Leverage the existing **LRU (Least Recently Used) Cache** for intermediate composite frames. This ensures "Instant Scrubbing" performance by storing pre-rendered textures in memory.
3. **Overlay Strategy:** Start with **Hybrid Rendering (QPainter)** for complex interactive handles (Scale/Rotate) but implement **GLSL-based Safe Area Guides** and Grids to reduce CPU overhead during static viewing.
4. **Color Pipeline:** **Standard sRGB/Linear Gamma Correction**. Implement a simple pass-through in the Master Shader to handle color space conversion correctly before display.



---

## Sub-Phase 3: Master Shader Implementation
**Goal:** Port OpenCV effects to GLSL.

### 3.1 `core/shaders/master_effect.glsl`
- Port current effects:
    - **Blur:** Multi-tap Gaussian or Box blur.
    - **VHS:** Chromatic aberration + Scanline distortion.
    - **Glow:** Threshold + Blur + Additive blend.
    - **Color:** Brightness, Contrast, Saturation, and LUT support.
    - **Glitch:** Block-based UV offset.

### 3.2 `core/render_engine.py` Refactor
- Modify `_composite_frame` to return a `RenderScene` list of dictionaries containing:
    - `texture_data`: Numpy array.
    - `uniforms`: Dictionary of effect parameters.
    - `transform`: Matrix for Pos/Scale/Rot/Crop.
- **Verification:** `tests/test_render_engine_gpu.py` - Feed a clip from `Project-05-06` and verify the `RenderScene` contains correct interpolated keyframe values.

---

## Sub-Phase 4: Hybrid Captions & Transitions
**Goal:** Complete the feature set.

### 4.1 Master Transition Shader
- Accept `texture_A`, `texture_B`, and `progress`.
- Implement standard wipes, fades, and glitch transitions.

### 4.2 Hybrid Captions
- `RenderEngine` continues to use `QPainter` to draw text to a transparent `QImage`.
- This `QImage` is uploaded as a texture and blended in `master_caption.glsl` (supporting GLSL-based glows or wipes on top of the text).

---

## Testing & Validation Strategy
1.  **Manual Test (Playback):** Use `Project-05-06`. Verify smooth 30fps playback of the video clip with keyframed overlays.
2.  **Regression Test:** Ensure interactive dragging/resizing of clips on the new `HiveViewport` works exactly like the old `TimelinePreviewCanvas`.
3.  **Effect Test:** Apply a "Cloud VHS" effect and verify it renders instantly without CPU spikes.
