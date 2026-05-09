# Phase 4.1: Visual Interaction (UI & UX for Store Integration)

## Objective
To build a professional, highly responsive, "CapCut-style" user interface for the Effects, Captions, and Transitions store. This phase focuses entirely on the visual experience, dragging/dropping, and asynchronous loading, preparing the UI to communicate with the GPU backend in later phases.

## 1. The Store Grid (Sidebar Layout)
*   **CapCut-Style Visual Grid:** The catalog will be displayed as a grid of thumbnails to prioritize visual exploration over text.
*   **Stateful Thumbnails:** 
    *   **Not Downloaded:** Displays a distinct "Cloud Install" icon instead of the actual effect preview.
    *   **Downloaded:** Displays the actual, high-quality thumbnail.
*   **Live Hover Previews:** Hovering over a downloaded item will play an animated preview of the effect/transition directly within the thumbnail, giving immediate visual feedback before applying.
*   **High-Performance Virtualization:**
    *   The list will strictly render only visible items (e.g., max 10 based on display height) to ensure zero lag during fast scrolling.
    *   Top (out-of-view) items will be aggressively offloaded from memory and reloaded seamlessly if the user scrolls up.
    *   An infinite-scroll "spinner" will appear at the bottom when fetching more items, ensuring the main thread never blocks so the user can continue editing.

## 2. Download UX & Async Handling
*   **Thumbnail Progress Ring:** While an item is downloading, an orange gradient ring will animate around the cloud icon.
*   **Async Timeline Loading:** Users do not have to wait. They can drag a "Cloud Icon" directly onto the timeline. The item will show the progress ring on the timeline clip, allowing the user to keep working while it fetches in the background.
*   **Visibility Optimization:** The UI will only calculate and render download progress animations for items currently visible on screen (in the sidebar or visible on the timeline) to save CPU cycles.
*   **Custom Toast System:** A new, reusable "Toast Notification" system will be built. If a download fails, a sleek, non-intrusive toast will slide in to notify the user.

## 3. Timeline Interactions & Tracks
*   **Application Methods:**
    *   **Drag & Drop:** Directly from the store to the timeline.
    *   **Double-Click:** Applies the effect to the currently selected clip.
    *   **Batch Apply:** Support for applying a setting across multiple selected items.
*   **Dedicated Track Architecture:**
    *   **Effects & Captions:** Can be applied directly onto a Video Clip *OR* placed on their own dedicated "Effects Track" or "Caption Track" to span multiple clips.
    *   **Transitions:** Strictly locked to the boundaries of Video (V) clips.
*   **Clip Badges:** When an effect is applied directly to a video clip, a small, clickable "FX" icon/badge will appear on that clip block in the timeline.

## 4. The Properties Panel & Keyframes
*   **Contextual Integration:** Settings for effects do not live in the store. When a user clicks an Effect block on the timeline (or clicks the FX badge on a video clip), the main Properties Panel will dynamically populate with the sliders/color pickers defined by that specific effect's JSON.
*   **Keyframe Engine UI:** The properties panel will include a UI for keyframing. Users will be able to click a "diamond" icon next to a property (e.g., Blur Intensity) to set keyframes, allowing effects to animate over time (e.g., a blur that fades in).

## Next Steps
Once this UI framework is approved and implemented, Phase 4.2 will handle the Backend Registry (mapping these UI elements to local files), and Phase 4.3 will handle the "Wiring" (sending these UI slider values directly to the Phase 3.3/3.4 GPU Shaders).
