import os
import re
import qtawesome as qta
from PySide6.QtWidgets import (QFileDialog, QVBoxLayout, QHBoxLayout, QWidget, 
                               QPushButton, QLineEdit, QComboBox)
from PySide6.QtCore import Qt

from core.media_manager import media_manager
from core.project_manager import project_manager
from core.app_config import app_config
from core.logger import hive_logger as logger
from ui.workspace_components.media_loader import MediaLoaderThread
from ui.workspace_components.draggable_card import DraggableCard

class MediaBinMixin:
    """Mixin for media bin management: importing, filtering, and organizing assets."""
    def _create_media_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        import_layout = QHBoxLayout()
        btn_import_files = QPushButton(qta.icon('mdi6.file-import-outline', color='#e66b2c'), " Import Files")
        btn_import_files.setStyleSheet(self.btn_style_primary)
        btn_import_files.setCursor(Qt.PointingHandCursor)
        btn_import_files.clicked.connect(self._import_media_files)
        
        btn_import_folder = QPushButton(qta.icon('mdi6.folder-plus-outline', color='#d1d1d1'), " Folder")
        btn_import_folder.setStyleSheet(self.btn_style_secondary)
        btn_import_folder.setCursor(Qt.PointingHandCursor)
        btn_import_folder.clicked.connect(self._import_folder)
        
        self.btn_media_up = QPushButton(qta.icon('mdi6.arrow-up-left', color='#d1d1d1'), "")
        self.btn_media_up.setStyleSheet("QPushButton { background: transparent; border: none; font-weight: bold; } QPushButton:hover { color: #ffffff; }")
        self.btn_media_up.setCursor(Qt.PointingHandCursor)
        self.btn_media_up.clicked.connect(self._navigate_media_up)
        self.btn_media_up.hide()
        
        import_layout.addWidget(btn_import_files, stretch=2)
        import_layout.addWidget(btn_import_folder, stretch=1)
        import_layout.addWidget(self.btn_media_up)
        layout.addLayout(import_layout)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(5)
        
        self.search_media = QLineEdit()
        self.search_media.setPlaceholderText("Search media...")
        self.search_media.setStyleSheet(self.input_style)
        self.search_media.textChanged.connect(self._apply_media_filters_and_sort)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Media", "Videos", "Images", "Audio", "Folders"])
        self.filter_combo.setStyleSheet(self.input_style)
        self.filter_combo.currentTextChanged.connect(self._apply_media_filters_and_sort)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Sort: Name", "Sort: Type", "Sort: Date Added"])
        self.sort_combo.setStyleSheet(self.input_style)
        self.sort_combo.currentTextChanged.connect(self._apply_media_filters_and_sort)
        
        self.btn_sort_order = QPushButton(qta.icon('mdi6.sort-alphabetical-ascending', color='#d1d1d1'), "")
        self.btn_sort_order.setStyleSheet(self.btn_style_secondary)
        self.btn_sort_order.setFixedSize(28, 28)
        self.btn_sort_order.setCursor(Qt.PointingHandCursor)
        self.btn_sort_order.clicked.connect(self._toggle_sort_order)
        
        filter_layout.addWidget(self.search_media, stretch=2)
        filter_layout.addWidget(self.filter_combo, stretch=1)
        filter_layout.addWidget(self.sort_combo, stretch=1)
        filter_layout.addWidget(self.btn_sort_order)
        layout.addLayout(filter_layout)

        self.media_scroll, self.media_grid = self._create_grid_scroll()
        layout.addWidget(self.media_scroll)
        return widget

    def clear_media_bin(self):
        logger.debug("MediaBin: Clearing media bin")
        while self.media_grid.count():
            item = self.media_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.all_media_cards.clear()

    def load_media_bin_from_paths(self, paths):
        logger.info(f"MediaBin: Loading bin from {len(paths)} paths")
        self.clear_media_bin()
        self.current_folder_path = None
        self.btn_media_up.hide()
        
        self._bulk_loading = True
        
        all_files_to_process = []
        valid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wav', '.mp3', '.aac', '.png', '.jpg', '.jpeg', '.webp'}
        
        processed_roots = set()
        for p in paths:
            p_norm = p.replace('\\', '/')
            if p_norm in processed_roots: continue
            processed_roots.add(p_norm)
            
            if os.path.exists(p) and os.path.isdir(p):
                self._add_folder_card(p)
                self._preload_folder_contents(p, valid_exts, all_files_to_process)
                
        files_to_process = [p for p in paths if os.path.exists(p) and not os.path.isdir(p)]
        all_files_to_process.extend([(f, None) for f in files_to_process])
        
        if not all_files_to_process:
            self._bulk_loading = False
            self._apply_media_filters_and_sort()
            return
        
        processed_files = set()
        unique_items = []
        for fpath, parent in all_files_to_process:
            if fpath in processed_files:
                continue
            processed_files.add(fpath)
            unique_items.append((fpath, parent))
        
        self._pending_batches = 1
        self.media_load_started.emit()
        
        self._process_media_files_async(unique_items, False, None, parent_folder=None, suppress_signals=True)
    
    def _preload_folder_contents(self, folder_path, valid_exts, collect_list):
        """Recursively scan a folder and collect media files."""
        folder_path = folder_path.replace('\\', '/')
        try:
            for f in os.listdir(folder_path):
                full_path = os.path.join(folder_path, f).replace('\\', '/')
                if os.path.isdir(full_path):
                    self._add_folder_card_with_parent(full_path, folder_path)
                    self._preload_folder_contents(full_path, valid_exts, collect_list)
                else:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        collect_list.append((full_path, folder_path))
        except Exception as e:
            logger.debug(f"MediaBin: Preload error for {folder_path}: {e}")
    
    def _add_folder_card_with_parent(self, folder_path, parent_folder):
        folder_path = folder_path.replace('\\', '/')
        parent_folder = parent_folder.replace('\\', '/') if parent_folder else None
        if any(c.file_path == folder_path for c in self.all_media_cards):
            return
            
        card = DraggableCard(
            title=os.path.basename(folder_path),
            icon_name='mdi6.folder',
            item_type='folder',
            subtype='folder',
            file_path=folder_path
        )
        card.card_clicked.connect(self._on_media_card_clicked)
        card.folder_double_clicked.connect(self._on_folder_double_clicked)
        card.date_added = os.path.getmtime(folder_path)
        card.parent_folder = parent_folder
        
        self.all_media_cards.append(card)

    def _import_media_files(self):
        default_dir = os.path.expanduser("~/Desktop")
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Media Files", default_dir, 
            "Media Files (*.mp4 *.mov *.avi *.mkv *.webm *.wav *.mp3 *.aac *.png *.jpg *.jpeg *.webp)"
        )
        if file_paths and project_manager.current_project:
            logger.info(f"MediaBin: Importing {len(file_paths)} files")
            self._handle_media_import(file_paths)

    def _import_folder(self):
        default_dir = os.path.expanduser("~/Desktop")
        folder_path = QFileDialog.getExistingDirectory(self, "Import Media Folder", default_dir)
        if folder_path and project_manager.current_project:
            folder_path = folder_path.replace('\\', '/')
            logger.info(f"MediaBin: Importing folder {folder_path}")
            if not self._is_path_covered(folder_path):
                project_manager.current_project.media_bin.append(folder_path)
                project_manager.save_project()
                
            if not self.current_folder_path:
                self._add_folder_card(folder_path)
                
            all_files_to_process = []
            valid_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wav', '.mp3', '.aac', '.png', '.jpg', '.jpeg', '.webp'}
            self._preload_folder_contents(folder_path, valid_exts, all_files_to_process)
            
            if not all_files_to_process:
                self._refresh_media_view()
                return
                
            processed_files = set()
            unique_items = []
            for fpath, parent in all_files_to_process:
                if fpath in processed_files: continue
                processed_files.add(fpath)
                unique_items.append((fpath, parent))
                
            self._bulk_loading = True
            was_pending = self._pending_batches
            self._pending_batches += 1
            
            if was_pending <= 0:
                self.media_load_started.emit()
                
            self._process_media_files_async(unique_items, False, None, parent_folder=None, suppress_signals=True)
            self._refresh_media_view()

    def _navigate_media_up(self):
        if self.current_folder_path:
            parent = os.path.dirname(self.current_folder_path).replace('\\', '/')
            logger.debug(f"MediaBin: Navigating up from {self.current_folder_path}")
            normalized_project_bins = [p.replace('\\', '/') for p in project_manager.current_project.media_bin]
            if any(p.startswith(parent) for p in normalized_project_bins):
                self.current_folder_path = parent if parent in normalized_project_bins else None
            else:
                self.current_folder_path = None
            self._refresh_media_view()

    def _refresh_media_view(self):
        if self.current_folder_path:
            self.btn_media_up.show()
        else:
            self.btn_media_up.hide()
        self._apply_media_filters_and_sort()
            
    def _add_folder_card(self, folder_path):
        folder_path = folder_path.replace('\\', '/')
        if any(c.file_path == folder_path for c in self.all_media_cards):
            return
            
        card = DraggableCard(
            title=os.path.basename(folder_path),
            icon_name='mdi6.folder',
            item_type='folder',
            subtype='folder',
            file_path=folder_path
        )
        card.card_clicked.connect(self._on_media_card_clicked)
        card.folder_double_clicked.connect(self._on_folder_double_clicked)
        card.date_added = os.path.getmtime(folder_path)
        card.parent_folder = self.current_folder_path
        
        self.all_media_cards.append(card)
        if not self._bulk_loading:
            self._apply_media_filters_and_sort()

    def _on_folder_double_clicked(self, folder_path):
        logger.debug(f"MediaBin: Entering folder {folder_path}")
        self.current_folder_path = folder_path.replace('\\', '/')
        self.btn_media_up.show()
        self._apply_media_filters_and_sort()
                
    def _handle_media_import(self, file_paths):
        copy_enabled = app_config.get_setting("copy_media_to_project", False)
        proj_dir = os.path.dirname(project_manager.project_path) if project_manager.project_path else None
        
        media_dir = None
        if copy_enabled and proj_dir:
            media_dir = os.path.join(proj_dir, "media")
            os.makedirs(media_dir, exist_ok=True)
            
        self._process_media_files_async(file_paths, copy_enabled, media_dir, parent_folder=self.current_folder_path)

    def _process_media_files_async(self, file_paths, copy_enabled=False, dest_dir=None, parent_folder=None, suppress_signals=False):
        if not file_paths: return
        
        existing_paths = {c.file_path for c in self.all_media_cards}
        filtered_paths = []
        for item in file_paths:
            p = item[0] if isinstance(item, tuple) else item
            if p.replace('\\', '/') not in existing_paths:
                filtered_paths.append(item)
        
        if not filtered_paths:
            if not suppress_signals:
                self.media_load_finished.emit()
            elif self._pending_batches > 0:
                self._on_import_batch_finished()
            return
            
        if not suppress_signals:
            self._pending_batches = 1
            self.media_load_started.emit()
        
        logger.info(f"MediaBin: Starting async load for {len(filtered_paths)} items")
        thread = MediaLoaderThread(filtered_paths, copy_enabled, dest_dir, parent_folder)
        self.active_threads.add(thread)
        
        thread.item_processed.connect(self._add_media_card_to_grid)
        thread.finished_all.connect(self._on_import_batch_finished)
        
        thread.finished.connect(lambda t=thread: self.active_threads.discard(t) if t in getattr(self, 'active_threads', set()) else None)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_import_batch_finished(self):
        self._pending_batches = max(0, self._pending_batches - 1)
        
        if self._pending_batches <= 0:
            logger.info("MediaBin: All import batches finished")
            self._bulk_loading = False
            self._apply_media_filters_and_sort()
            project_manager.save_project()
            self.media_load_finished.emit()

    def _add_media_card_to_grid(self, media_info, parent_folder):
        final_path = media_info["path"].replace('\\', '/')
        
        if not self._is_path_covered(final_path):
            project_manager.current_project.media_bin.append(final_path)

        if any(c.file_path == final_path for c in self.all_media_cards):
            return

        card = DraggableCard(
            title=media_info["name"],
            icon_name=media_info["icon"],
            item_type="media",
            subtype=media_info["type"],
            file_path=final_path,
            thumbnail=media_info["thumbnail"],
            duration=media_info.get("duration", 0.0),
        )
        card.date_added = os.path.getmtime(final_path) if os.path.exists(final_path) else 0
        card.parent_folder = parent_folder.replace('\\', '/') if parent_folder else None
        
        card.add_requested.connect(self.add_item_to_timeline.emit)
        card.preview_requested.connect(self.preview_requested.emit)
        card.card_clicked.connect(self._on_media_card_clicked)
        
        self.all_media_cards.append(card)
        if not self._bulk_loading:
            self._apply_media_filters_and_sort()

        if media_info["type"] == "video" and app_config.get_setting("auto_proxies", True):
            media_manager.start_proxy_generation(
                final_path,
                on_progress_callback=self._handle_proxy_progress,
                on_finish_callback=self._handle_proxy_finished,
                on_fail_callback=self._handle_proxy_failed 
            )

    def _toggle_sort_order(self):
        self.sort_asc = not self.sort_asc
        logger.debug(f"MediaBin: Toggling sort order to {'asc' if self.sort_asc else 'desc'}")
        icon = 'mdi6.sort-alphabetical-ascending' if self.sort_asc else 'mdi6.sort-alphabetical-descending'
        self.btn_sort_order.setIcon(qta.icon(icon, color='#d1d1d1'))
        self._apply_media_filters_and_sort()

    def _apply_media_filters_and_sort(self):
        search_txt = self.search_media.text().lower()
        filter_txt = self.filter_combo.currentText()
        sort_txt = self.sort_combo.currentText()
        
        def natural_sort_key(card):
            return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', card.title)]
            
        curr_pf = self.current_folder_path.replace('\\', '/') if self.current_folder_path else None
        
        visible_cards = []
        for card in self.all_media_cards:
            card_pf = card.parent_folder.replace('\\', '/') if card.parent_folder else None
            
            if card_pf != curr_pf:
                card.hide()
                continue

            matches_filter = True
            if filter_txt == "Videos" and card.subtype != "video": matches_filter = False
            elif filter_txt == "Images" and card.subtype != "image": matches_filter = False
            elif filter_txt == "Audio" and card.subtype != "audio": matches_filter = False
            elif filter_txt == "Folders" and card.item_type != "folder": matches_filter = False
            
            matches_search = (search_txt in card.title.lower()) if search_txt else True
            
            if matches_filter and matches_search:
                visible_cards.append(card)
                card.show()
            else:
                card.hide()
                card.is_selected = False
                card.setStyleSheet(card.default_style)
                
        if "Name" in sort_txt:
            visible_cards.sort(key=natural_sort_key, reverse=not self.sort_asc)
        elif "Type" in sort_txt:
            visible_cards.sort(key=lambda c: c.subtype, reverse=not self.sort_asc)
        elif "Date" in sort_txt:
            visible_cards.sort(key=lambda c: getattr(c, "date_added", 0), reverse=not self.sort_asc)
            
        while self.media_grid.count():
            self.media_grid.takeAt(0)
            
        row, col = 0, 0
        for card in visible_cards:
            self.media_grid.addWidget(card, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1

    def _on_media_card_clicked(self, card, modifiers):
        all_visible = [c for c in self.all_media_cards if c.isVisible()]
                
        if modifiers & Qt.ControlModifier:
            card.is_selected = not card.is_selected
            card.setStyleSheet(card.selected_style if card.is_selected else card.default_style)
            self.last_clicked_card = card
        elif modifiers & Qt.ShiftModifier and self.last_clicked_card:
            try:
                idx1 = all_visible.index(self.last_clicked_card)
                idx2 = all_visible.index(card)
                start, end = min(idx1, idx2), max(idx1, idx2)
                for i in range(start, end + 1):
                    all_visible[i].is_selected = True
                    all_visible[i].setStyleSheet(all_visible[i].selected_style)
            except ValueError:
                pass
        else:
            for c in all_visible:
                if c != card:
                    c.is_selected = False
                    c.setStyleSheet(c.default_style)
            card.is_selected = True
            card.setStyleSheet(card.selected_style)
            self.last_clicked_card = card

    def _handle_proxy_progress(self, original_path, percentage):
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(percentage)

    def _handle_proxy_finished(self, original_path, proxy_path):
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(100)
                card.set_proxy_path(proxy_path)
            
    def _handle_proxy_failed(self, original_path, error_msg):
        logger.error(f"MediaBin: Proxy generation failed for {original_path}: {error_msg}")
        for card in self.all_media_cards:
            if card.file_path == original_path:
                card.update_proxy_progress(100)

    def _is_path_covered(self, target_path):
        if not project_manager.current_project:
            return False
            
        target_path = target_path.replace('\\', '/')
        for entry in project_manager.current_project.media_bin:
            entry_norm = entry.replace('\\', '/')
            if target_path == entry_norm:
                return True
            if os.path.isdir(entry) and target_path.startswith(entry_norm.rstrip('/') + '/'):
                return True
        return False
