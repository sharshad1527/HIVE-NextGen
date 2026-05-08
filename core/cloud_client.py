import os
import json
import requests
import hashlib
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread, QRunnable, QThreadPool
from core.logger import hive_logger
from core.app_config import app_config

class UpdateWorker(QThread):
    """
    Dedicated thread to fetch and compare the remote catalog.
    """
    update_data_ready = Signal(dict, bool) # data, updated
    error = Signal(str)

    def __init__(self, catalog_url, local_file):
        super().__init__()
        self.catalog_url = catalog_url
        self.local_file = local_file

    def run(self):
        try:
            hive_logger.info(f"[CloudClient] Checking for catalog updates at {self.catalog_url}")
            
            # Fetch remote catalog
            response = requests.get(self.catalog_url, timeout=10)
            response.raise_for_status()
            remote_data = response.json()
            
            updated = True
            if self.local_file.exists():
                with open(self.local_file, "rb") as f:
                    local_hash = hashlib.md5(f.read()).hexdigest()
                remote_hash = hashlib.md5(response.content).hexdigest()
                
                if local_hash == remote_hash:
                    hive_logger.info("[CloudClient] Catalog is already up to date.")
                    updated = False
            
            if updated:
                self.local_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.local_file, "wb") as f:
                    f.write(response.content)
                hive_logger.info("[CloudClient] Catalog updated successfully.")
            
            self.update_data_ready.emit(remote_data, updated)
        except Exception as e:
            hive_logger.error(f"[CloudClient] Catalog update failed: {e}")
            self.error.emit(str(e))

class DownloadWorker(QRunnable):
    """
    Worker to handle individual file downloads in the background.
    """
    def __init__(self, url, dest_path, item_id, file_type):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self.item_id = item_id
        self.file_type = file_type # 'json' or 'thumb'

    def run(self):
        try:
            hive_logger.debug(f"[CloudClient] Downloading {self.file_type} for {self.item_id} from {self.url}")
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            
            self.dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.dest_path, "wb") as f:
                f.write(response.content)
            
            hive_logger.debug(f"[CloudClient] Successfully downloaded {self.file_type} to {self.dest_path}")
        except Exception as e:
            hive_logger.error(f"[CloudClient] Failed to download {self.file_type} for {self.item_id}: {e}")

class CloudStoreClient(QObject):
    """
    Async client to manage H.I.V.E Cloud Store operations.
    Handles catalog updates and background preset downloads.
    """
    catalog_updated = Signal(dict)
    download_finished = Signal(str, bool) # item_id, success
    error_occurred = Signal(str)

    CATALOG_URL = "https://raw.githubusercontent.com/sharshad1527/HIVE-Effects-Store/main/store_catalog.json"

    def __init__(self):
        super().__init__()
        self.cache_dir = app_config.config_dir / "cloud_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_file = self.cache_dir / "store_catalog.json"
        self.thread_pool = QThreadPool.globalInstance()
        
        self.catalog_data = self._load_local_catalog()
        self._updater = None

    def _load_local_catalog(self) -> dict:
        """Loads the catalog from disk if it exists."""
        if self.catalog_file.exists():
            try:
                with open(self.catalog_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                hive_logger.error(f"[CloudClient] Failed to load local catalog: {e}")
        return {}

    def check_and_update_catalog(self):
        """
        Fetches the remote catalog and updates if it has changed.
        Prevents multiple concurrent updates.
        """
        if self._updater and self._updater.isRunning():
            hive_logger.debug("[CloudClient] Catalog update already in progress, skipping redundant request.")
            return

        self._updater = UpdateWorker(self.CATALOG_URL, self.catalog_file)
        self._updater.update_data_ready.connect(self._on_catalog_update_finished)
        self._updater.error.connect(lambda e: self.error_occurred.emit(e))
        
        # Clean up reference when finished to allow future updates
        # Use built-in QThread.finished for safe cleanup after run() exits
        self._updater.finished.connect(self._clear_updater)
        self._updater.finished.connect(self._updater.deleteLater)
        self._updater.error.connect(self._clear_updater)

        self._updater.start()

    def _clear_updater(self, *args):
        """Called when thread finishes to clear the reference safely."""
        self._updater = None

    def _on_catalog_update_finished(self, data, updated):
        self.catalog_data = data
        if updated:
            self.catalog_updated.emit(data)

    def download_preset(self, item_id: str):
        """
        Finds the preset in the catalog and starts downloading its files.
        """
        if not self.catalog_data:
            self.error_occurred.emit("Catalog not loaded.")
            return

        # Find item in catalog
        item = None
        for category in self.catalog_data.get("categories", []):
            for i in category.get("items", []):
                if i["id"] == item_id:
                    item = i
                    break
            if item: break

        if not item:
            self.error_occurred.emit(f"Item {item_id} not found in catalog.")
            return

        cdn_root = self.catalog_data.get("cdn_root", "")
        json_url = cdn_root + item["file"]
        thumb_url = cdn_root + item["thumb"]
        
        json_path = self.cache_dir / item["file"]
        thumb_path = self.cache_dir / item["thumb"]

        # Background downloads
        json_worker = DownloadWorker(json_url, json_path, item_id, "json")
        thumb_worker = DownloadWorker(thumb_url, thumb_path, item_id, "thumb")
        
        self.thread_pool.start(json_worker)
        self.thread_pool.start(thumb_worker)
        
        self.download_finished.emit(item_id, True)
        hive_logger.info(f"[CloudClient] Started download for {item_id}")

    def is_preset_downloaded(self, item_id: str) -> bool:
        """Checks if both the JSON and thumbnail for a preset exist locally."""
        if not self.catalog_data:
            return False
            
        item = None
        for category in self.catalog_data.get("categories", []):
            for i in category.get("items", []):
                if i["id"] == item_id:
                    item = i
                    break
            if item: break
            
        if not item:
            return False
            
        json_path = self.cache_dir / item["file"]
        thumb_path = self.cache_dir / item["thumb"]
        
        return json_path.exists() and thumb_path.exists()

# Global instance
cloud_client = CloudStoreClient()
