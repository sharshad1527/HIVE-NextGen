import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from PySide6.QtCore import QCoreApplication, QTimer
from core.cloud_client import cloud_client
from core.logger import logger_manager

def run_test():
    app = QCoreApplication(sys.argv)
    
    # Initialize logger
    logger_manager.setup(project_root / "logs", verbose=True)
    
    print("--- Starting CloudStoreClient Test ---")
    
    def on_catalog_updated(data):
        print(f"Catalog updated! Version: {data.get('version')}")
        print(f"Categories: {[c['name'] for c in data.get('categories', [])]}")
        
        # Test download
        item_id = "blur"
        print(f"Testing download for: {item_id}")
        cloud_client.download_preset(item_id)

    def on_download_finished(item_id, success):
        print(f"Download finished for {item_id}: {'Success' if success else 'Failed'}")
        
        # Check if files exist
        if cloud_client.is_preset_downloaded(item_id):
            print(f"Verification: Files for {item_id} exist in cache.")
        else:
            print(f"Verification: Files for {item_id} NOT found in cache (might still be downloading).")
        
        # Exit after a short delay to allow background threads to finish if they were still writing
        QTimer.singleShot(2000, app.quit)

    def on_error(msg):
        print(f"Error occurred: {msg}")
        app.quit()

    cloud_client.catalog_updated.connect(on_catalog_updated)
    cloud_client.download_finished.connect(on_download_finished)
    cloud_client.error_occurred.connect(on_error)

    # Trigger update
    print("Checking catalog...")
    cloud_client.check_and_update_catalog()
    
    # If catalog is already up to date, it won't emit catalog_updated.
    # We should handle that case for the test.
    def check_already_updated():
        if cloud_client.catalog_data and not cloud_client.updater.isRunning():
            print("Catalog was already up to date or update finished quickly.")
            on_catalog_updated(cloud_client.catalog_data)
            
    QTimer.singleShot(3000, check_already_updated)

    sys.exit(app.exec())

if __name__ == "__main__":
    run_test()
