import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from PySide6.QtWidgets import QApplication, QListView, QVBoxLayout, QWidget, QLineEdit
from PySide6.QtCore import Qt, QSortFilterProxyModel
from ui.preset_model import PresetModel
from ui.preset_delegate import PresetDelegate

def run_performance_test():
    app = QApplication(sys.argv)
    
    # Create a dummy model and fill with 5000 items
    class DummyPresetModel(PresetModel):
        def refresh(self):
            self.beginResetModel()
            self._items = []
            for i in range(5000):
                self._items.append({
                    "id": f"dummy_{i}",
                    "name": f"High Perf Preset {i}",
                    "icon": "mdi6.auto-fix",
                    "type": "effect",
                    "subtype": "blur",
                    "_is_cloud": True
                })
            self.endResetModel()

    window = QWidget()
    window.setWindowTitle("H.I.V.E Virtualization Test (5,000 Items)")
    window.resize(400, 600)
    layout = QVBoxLayout(window)
    
    search = QLineEdit()
    search.setPlaceholderText("Filter 5,000 items...")
    layout.addWidget(search)
    
    source_model = DummyPresetModel("effects")
    source_model.refresh()
    
    proxy_model = QSortFilterProxyModel()
    proxy_model.setSourceModel(source_model)
    proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
    proxy_model.setFilterRole(PresetModel.NameRole)
    search.textChanged.connect(proxy_model.setFilterFixedString)
    
    view = QListView()
    view.setModel(proxy_model)
    view.setViewMode(QListView.IconMode)
    view.setResizeMode(QListView.Adjust)
    view.setMovement(QListView.Static)
    view.setSpacing(10)
    
    delegate = PresetDelegate(view)
    view.setItemDelegate(delegate)
    
    layout.addWidget(view)
    window.show()
    
    print("UI Loaded with 5,000 items. Test scrolling and filtering.")
    sys.exit(app.exec())

if __name__ == "__main__":
    run_performance_test()
