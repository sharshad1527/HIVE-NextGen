from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, Signal
from core.cloud_client import cloud_client
from core.preset_loader import get_presets
import os
import time

class PresetModel(QAbstractListModel):
    """
    Unified model for Local and Cloud presets.
    Supports virtualization and track download states.
    """
    NameRole = Qt.UserRole + 1
    IconRole = Qt.UserRole + 2
    TypeRole = Qt.UserRole + 3
    SubtypeRole = Qt.UserRole + 4
    PathRole = Qt.UserRole + 5
    ThumbRole = Qt.UserRole + 6
    PropertiesRole = Qt.UserRole + 7
    DownloadStateRole = Qt.UserRole + 8 # 0: Local, 1: Cloud, 2: Downloading
    IDRole = Qt.UserRole + 9

    # Download States
    STATE_LOCAL = 0
    STATE_CLOUD = 1
    STATE_DOWNLOADING = 2

    def __init__(self, category_id, parent=None):
        super().__init__(parent)
        self.category_id = category_id # 'effects', 'transitions', 'captions'
        self._items = []
        self._downloading_ids = set()
        self._newly_downloaded = {} # item_id -> timestamp
        
        # Connect to cloud client signals
        cloud_client.catalog_updated.connect(self.refresh)
        cloud_client.download_finished.connect(self._on_download_finished)

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item = self._items[index.row()]
        
        if role == self.NameRole: return item.get("name")
        if role == self.IconRole: return item.get("icon", "mdi6.auto-fix")
        if role == self.IDRole: return item.get("id")
        
        # Consistent Type/Subtype mapping
        if role == self.TypeRole:
            if self.category_id == "captions": return "caption"
            if self.category_id == "effects": return "effect"
            if self.category_id == "transitions": return "transition"
            return "preset"
        
        if role == self.SubtypeRole: return item.get("subtype") or item.get("name")
        
        # Path Resolution (Handle Cloud Cache)
        if role == self.PathRole:
            raw_path = item.get("_source_file") or item.get("file")
            if raw_path and not os.path.isabs(raw_path):
                cached_path = cloud_client.cache_dir / raw_path
                if cached_path.exists(): return str(cached_path)
            return raw_path

        if role == self.ThumbRole:
            raw_thumb = item.get("thumbnail") or item.get("thumb")
            if raw_thumb and not os.path.isabs(raw_thumb):
                cached_thumb = cloud_client.cache_dir / raw_thumb
                if cached_thumb.exists(): return str(cached_thumb)
            return raw_thumb

        if role == self.PropertiesRole: return item.get("properties", {})
        
        if role == self.DownloadStateRole:
            item_id = item.get("id")
            if not item_id: return self.STATE_LOCAL # Local items might not have IDs
            
            if item_id in self._downloading_ids:
                return self.STATE_DOWNLOADING
            
            # Check if it's already local (either in presets/ or in cache/)
            if item.get("_is_cloud"):
                if cloud_client.is_preset_downloaded(item_id):
                    return self.STATE_LOCAL
                return self.STATE_CLOUD
            return self.STATE_LOCAL

        return None

    def refresh(self):
        """Reloads items from local storage and cloud catalog."""
        self.beginResetModel()
        
        # 1. Get Local Presets
        local_presets = get_presets(self.category_id, force_reload=True)
        for p in local_presets:
            p["_is_cloud"] = False
            # Try to match with an ID if possible, otherwise use name
            if "id" not in p:
                p["id"] = p["name"].lower().replace(" ", "_")
        
        # 2. Get Cloud Presets from Catalog
        cloud_items = []
        if cloud_client.catalog_data:
            for cat in cloud_client.catalog_data.get("categories", []):
                if cat["id"] == self.category_id:
                    for item in cat.get("items", []):
                        # Avoid duplicates if already local
                        local_ids = {p["id"] for p in local_presets}
                        if item["id"] not in local_ids:
                            item["_is_cloud"] = True
                            cloud_items.append(item)
                    break
        
        self._items = local_presets + cloud_items
        self.endResetModel()

    def start_download(self, row):
        if row < 0 or row >= len(self._items): return
        
        item = self._items[row]
        item_id = item.get("id")
        if not item_id or not item.get("_is_cloud"): return
        
        self._downloading_ids.add(item_id)
        cloud_client.download_preset(item_id)
        
        # Notify view to update this row
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [self.DownloadStateRole])

    def _on_download_finished(self, item_id, success):
        if item_id in self._downloading_ids:
            self._downloading_ids.discard(item_id)
            
            # Track newly downloaded for glow effect
            if success:
                self._newly_downloaded[item_id] = time.time()
            
            # Find the row and notify update
            for i, item in enumerate(self._items):
                if item.get("id") == item_id:
                    idx = self.index(i)
                    self.dataChanged.emit(idx, idx, [self.DownloadStateRole])
                    break

    def get_download_time(self, item_id):
        return self._newly_downloaded.get(item_id, 0)
