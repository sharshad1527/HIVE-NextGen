import pytest
from PySide6.QtWidgets import QApplication, QFrame
from ui.workspace import WorkspacePanel

# Create QApplication if it doesn't exist (needed for widget tests)
if not QApplication.instance():
    app = QApplication([])

def test_workspace_panel_methods():
    """Verify that all expected methods are present in the refactored WorkspacePanel."""
    panel = WorkspacePanel()
    
    # Core Methods
    assert hasattr(panel, "_init_base_state")
    assert hasattr(panel, "_init_ui")
    
    # Media Bin Mixin Methods
    assert hasattr(panel, "clear_media_bin")
    assert hasattr(panel, "load_media_bin_from_paths")
    assert hasattr(panel, "_import_media_files")
    assert hasattr(panel, "_apply_media_filters_and_sort")
    
    # Effect Store Mixin Methods
    assert hasattr(panel, "_create_preset_tab")
    assert hasattr(panel, "_on_preset_add_requested")
    
    # Layout Mixin Methods
    assert hasattr(panel, "switch_tab")
    assert hasattr(panel, "_create_workspace_tab")
    
    # Sync Mixin Methods
    assert hasattr(panel, "_on_project_loaded")
    assert hasattr(panel, "_open_project_settings")
    
    # Signals
    assert hasattr(panel, "add_item_to_timeline")
    assert hasattr(panel, "preview_requested")
    assert hasattr(panel, "media_load_started")
    assert hasattr(panel, "media_load_finished")

def test_workspace_panel_inheritance():
    """Ensure proper inheritance order."""
    panel = WorkspacePanel()
    assert isinstance(panel, QFrame)
    
    # Check MRO order - WorkspacePanel should be first, QFrame last (before object)
    mro = WorkspacePanel.mro()
    assert mro[0] == WorkspacePanel
    assert QFrame in mro
    assert mro.index(QFrame) > mro.index(WorkspacePanel)

def test_workspace_panel_ui_init():
    """Verify that the UI initializes without error and has expected tabs."""
    panel = WorkspacePanel()
    assert panel.stack.count() == 5
    assert len(panel.tab_buttons) == 5
    assert panel.objectName() == "Panel"
