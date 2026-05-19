import os
import shutil
from PySide6.QtCore import QThread, Signal
from core.media_manager import media_manager
from core.logger import hive_logger as logger

class MediaLoaderThread(QThread):
    """Background thread for processing media files (copying and metadata extraction)."""
    item_processed = Signal(dict, str)
    finished_all = Signal()
    
    def __init__(self, items, copy_enabled=False, dest_dir=None, parent_folder=None):
        super().__init__()
        self.items = items
        self.copy_enabled = copy_enabled
        self.dest_dir = dest_dir
        self.default_parent = parent_folder
        
    def run(self):
        logger.info(f"MediaLoaderThread started: processing {len(self.items)} items")
        for item in self.items:
            if isinstance(item, tuple):
                path, p_folder = item
            else:
                path = item
                p_folder = self.default_parent
                
            final_path = path
            
            if self.copy_enabled and self.dest_dir:
                filename = os.path.basename(path)
                dest_path = os.path.join(self.dest_dir, filename).replace('\\', '/')
                
                if not os.path.exists(dest_path) or os.path.abspath(path) != os.path.abspath(dest_path):
                    try:
                        shutil.copy2(path, dest_path)
                        final_path = dest_path
                    except Exception as e:
                        logger.error(f"Failed to copy media file {path}: {e}")
            
            info = media_manager.process_file(final_path)
            if info:
                self.item_processed.emit(info, p_folder)
                
        self.finished_all.emit()
        logger.info("MediaLoaderThread finished")
