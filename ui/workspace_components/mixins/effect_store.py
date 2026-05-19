from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QWidget, 
                               QLineEdit, QComboBox, QListView)
from PySide6.QtCore import Qt, QSortFilterProxyModel
from ui.preset_model import PresetModel
from ui.preset_delegate import PresetDelegate
from core.cloud_client import cloud_client
from core.logger import hive_logger as logger

class EffectStoreMixin:
    """Mixin for the effect store UI: browsing, searching, and adding presets/effects."""
    def _create_preset_tab(self, category, default_icon, placeholders):
        logger.debug(f"EffectStore: Creating tab for category {category}")
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        search = QLineEdit()
        search.setPlaceholderText(f"Search {category}...")
        search.setStyleSheet(self.input_style)
        
        filter_combo = QComboBox()
        filter_combo.addItems(["All", "Favorites", "Trending"])
        filter_combo.setStyleSheet(self.input_style)
        filter_combo.setFixedWidth(90)
        
        top_layout.addWidget(search)
        top_layout.addWidget(filter_combo)
        layout.addLayout(top_layout)

        category_folder_map = { "Captions": "captions", "Effects": "effects", "Transitions": "transitions" }
        folder_name = category_folder_map.get(category, category.lower())
        
        source_model = PresetModel(folder_name)
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
        view.setWordWrap(True)
        view.setDragEnabled(True)
        view.setDragDropMode(QListView.DragOnly)
        view.setDefaultDropAction(Qt.CopyAction)
        view.setStyleSheet("""
            QListView { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 0px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
            QScrollBar::handle:vertical:hover { background: #555; }
        """)
        
        delegate = PresetDelegate(view)
        view.setItemDelegate(delegate)
        
        delegate.add_requested.connect(lambda row: self._on_preset_add_requested(proxy_model, row))
        
        def handle_download(proxy_row):
            source_idx = proxy_model.mapToSource(proxy_model.index(proxy_row, 0))
            logger.info(f"EffectStore: Download requested for {category} item {source_idx.row()}")
            source_model.start_download(source_idx.row())
            
        delegate.download_requested.connect(handle_download)

        layout.addWidget(view)
        cloud_client.check_and_update_catalog()
        
        return widget

    def _on_preset_add_requested(self, model, row):
        idx = model.index(row, 0)
        title = idx.data(PresetModel.NameRole)
        logger.info(f"EffectStore: Add requested for preset '{title}'")
        
        data = {
            "title": title,
            "type": idx.data(PresetModel.TypeRole),
            "subtype": idx.data(PresetModel.SubtypeRole),
            "file_path": idx.data(PresetModel.PathRole),
            "thumbnail": idx.data(PresetModel.ThumbRole),
            "preset_properties": idx.data(PresetModel.PropertiesRole)
        }
        self.add_item_to_timeline.emit(data)
