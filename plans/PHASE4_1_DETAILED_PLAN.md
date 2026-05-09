# Phase 4.1: Visual Interaction (UI & UX for Store Integration)

## Objective
Build a professional, highly responsive, "CapCut-style" user interface for the Effects, Captions, and Transitions store. Focus entirely on the visual experience, dragging/dropping, and asynchronous loading, preparing the UI to communicate with the GPU backend.

## 1. The Store Grid (Sidebar Layout)
*   **CapCut-Style Visual Grid:** Grid of thumbnails prioritizing visual exploration.
*   **Stateful Thumbnails:** 
    *   **Not Downloaded:** "Cloud Install" icon.
    *   **Downloaded:** High-quality thumbnail.
*   **Live Hover Previews:** Hovering plays an animated preview.
*   **High-Performance Virtualization:**
    *   Strictly render only visible items (max ~10) to ensure zero lag.
    *   Infinite-scroll "spinner" at the bottom for loading more items without blocking the main thread.

## 2. Download UX & Async Handling
*   **Thumbnail Progress Ring:** Orange gradient ring animates around the cloud icon during download.
*   **Async Timeline Loading:** Users can drag a "Cloud Icon" directly onto the timeline. It shows the progress ring on the clip itself.
*   **Visibility Optimization:** Only render download animations for on-screen items.
*   **Custom Toast System:** Reusable "Toast Notification" system for errors (e.g., download failed).

## 3. Timeline Interactions & Tracks
*   **Application Methods:**
    *   **Drag & Drop:** From store to timeline.
    *   **Double-Click:** Applies to the currently selected clip.
    *   **Batch Apply:** Support across multiple selected items.
*   **Dedicated Track Architecture:**
    *   **Effects & Captions:** Can be applied directly onto a Video Clip OR on dedicated "Effects/Caption Tracks".
    *   **Transitions:** Strictly locked to the boundaries of Video (V) clips.
*   **Clip Badges:** A clickable "FX" icon/badge on video clips that have direct effects.

## 4. The Properties Panel & Keyframes
*   **Contextual Integration:** Clicking an Effect block or FX badge dynamically populates the Properties Panel based on the effect's JSON.
*   **Keyframe Engine UI:** A "diamond" icon next to properties for keyframing.
