# Phase 3.1: Cloud Store & UI Virtualization

## Objective
Implement a professional, on-demand preset delivery system with a virtualized UI to handle thousands of items without performance degradation.

## 🛠 Architectural Changes
1.  **Conditional Fetching:** Implement logic to check the remote `store_catalog.json` modification date (using HTTP headers like `If-Modified-Since` or comparing file hashes) to avoid unnecessary downloads.
2.  **Async Client (`core/cloud_client.py`):** A robust manager to handle catalog parsing and background downloads (JSON + Thumbnails) using `QThread`.
3.  **UI Virtualization (`ui/workspace.py`):** Replace the static `QGridLayout` for presets with `QListView` and a custom `QAbstractListModel`.
4.  **Logging:** Mandatory debug logging using `hive_logger` for all network requests, file operations, and UI model updates.

## ✅ Implementation Steps

### 1.1 `CloudStoreClient` & Cache Manager
- Create `core/cloud_client.py`.
- Method `check_and_update_catalog()`: 
    - Compare local `store_catalog.json` timestamp/hash with GitHub.
    - Only download if changed.
- Method `download_preset(item_id)`:
    - Background task to fetch `.json` and `thumbnail.jpg`.
    - Save to `~/.hive_editor/cloud_cache/`.
- **Verification:** Test script to simulate a changed catalog and verify conditional download.

### 1.2 Model/View UI Refactor
- Create `ui/preset_model.py`:
    - Subclass `QAbstractListModel`.
    - Handle both `Local` and `Cloud` items.
    - Track "Download State" (Not Downloaded, Downloading, Local).
- Modify `ui/workspace.py`:
    - Replace `DraggableCard` grid with `QListView`.
    - Use a `QStyledItemDelegate` to render the CapCut-style preset cards with a "Cloud/Download" icon overlay.
- **Verification:** Fill the model with 5,000 dummy items and verify buttery-smooth scrolling.

### 1.3 Store Integration
- Connect the "Download" button (on the card) to the `CloudStoreClient`.
- Implement a "Glow Effect" on newly downloaded cards for 3 seconds.
- **Verification:** Click a cloud preset, wait for download, and verify it turns into a local preset in the UI.

## 🧪 Testing Protocol
- **Unit Test:** `tests/test_cloud_client.py` - Verify conditional fetch logic.
- **Performance Test:** `tests/test_virtual_list.py` - Measure FPS during rapid scrolling of 10,000 items.
- **Manual Test:** Use `Project-05-08`. Open the Effects tab, refresh catalog, download a new effect, and apply it.

## 🤖 Agent Instructions
- **THINKING & CODING:** Use **PRO MODEL**.
- **SIMPLE TASKS:** Use Flash/Lite.
- **DEBUGGING:** Ensure every network call and model update is logged to `hive_logger`.
