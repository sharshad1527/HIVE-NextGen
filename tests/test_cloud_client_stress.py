import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from PySide6.QtCore import QCoreApplication, QTimer
from core.cloud_client import cloud_client
from core.logger import logger_manager

def run_stress_test():
    app = QCoreApplication(sys.argv)
    
    # Initialize logger
    logger_manager.setup(project_root / "logs", verbose=True)
    
    print("--- Starting CloudStoreClient Stress Test ---")
    
    def on_finished(*args):
        print("Test finished successfully without crash.")
        QTimer.singleShot(2000, app.quit)

    cloud_client.catalog_updated.connect(on_finished)
    cloud_client.error_occurred.connect(lambda e: print(f"Error: {e}") or app.quit())

    print("Triggering multiple rapid catalog updates...")
    cloud_client.check_and_update_catalog()
    cloud_client.check_and_update_catalog()
    cloud_client.check_and_update_catalog()
    cloud_client.check_and_update_catalog()
    
    # If already up to date, it might not emit catalog_updated.
    # We check the thread state.
    def check_done():
        if not cloud_client._updater or not cloud_client._updater.isRunning():
            print("Updates finished or were skipped correctly.")
            on_finished()
            
    QTimer.singleShot(5000, check_done)

    sys.exit(app.exec())

if __name__ == "__main__":
    run_stress_test()
