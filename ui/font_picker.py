# ui/font_picker.py
"""
Professional searchable font picker with favorites, recent fonts,
and Google Fonts download integration.
"""

import qtawesome as qta
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLabel, QLineEdit, QScrollArea, QFrame,
                               QDialog, QProgressBar, QGridLayout, QMessageBox)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QColor

from core.font_manager import font_manager


class FontItemWidget(QFrame):
    """Single font row in the picker list."""
    clicked = Signal(str)
    favorite_toggled = Signal(str)
    
    def __init__(self, family_name, is_favorite=False, is_downloaded=False, parent=None):
        super().__init__(parent)
        self.family_name = family_name
        self.setFixedHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        
        self._default_style = """
            QFrame { background: transparent; border: none; border-radius: 4px; }
            QFrame:hover { background-color: rgba(230, 107, 44, 0.15); }
        """
        self._selected_style = """
            QFrame { background-color: rgba(230, 107, 44, 0.3); border: none; border-radius: 4px; }
        """
        self.setStyleSheet(self._default_style)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        
        # Favorite star
        self.btn_fav = QPushButton()
        self.btn_fav.setFixedSize(20, 20)
        self.btn_fav.setCursor(Qt.PointingHandCursor)
        self.btn_fav.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._update_fav_icon(is_favorite)
        self.btn_fav.clicked.connect(lambda: self.favorite_toggled.emit(self.family_name))
        layout.addWidget(self.btn_fav)
        
        # Font name label (rendered in own font)
        self.lbl_name = QLabel(family_name)
        display_font = QFont(family_name, 11)
        self.lbl_name.setFont(display_font)
        self.lbl_name.setStyleSheet("color: #d1d1d1; border: none;")
        layout.addWidget(self.lbl_name, stretch=1)
        
        # Downloaded badge
        if is_downloaded:
            badge = QLabel("DL")
            badge.setStyleSheet("color: #4CAF50; font-size: 8px; font-weight: bold; border: none;")
            layout.addWidget(badge)
    
    def _update_fav_icon(self, is_fav):
        icon_name = 'mdi6.star' if is_fav else 'mdi6.star-outline'
        color = '#FFD700' if is_fav else '#555555'
        self.btn_fav.setIcon(qta.icon(icon_name, color=color))
    
    def set_favorite(self, is_fav):
        self._update_fav_icon(is_fav)
    
    def set_selected(self, selected):
        self.setStyleSheet(self._selected_style if selected else self._default_style)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.family_name)


class FontDownloadDialog(QDialog):
    """Dialog for browsing and downloading Google Fonts."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Download Google Fonts")
        self.setFixedSize(480, 560)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #111111;
                border: 1px solid #262626;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        
        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("background-color: #151515; border-bottom: 1px solid #262626; border-top-left-radius: 10px; border-top-right-radius: 10px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        lbl_title = QLabel("Google Fonts Library")
        lbl_title.setStyleSheet("color: #d1d1d1; font-weight: bold; font-size: 12px; border: none;")
        
        btn_close = QPushButton(qta.icon('mdi6.close', color='#808080'), "")
        btn_close.setFixedSize(24, 24)
        btn_close.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #ff3b30; border-radius: 4px; }")
        btn_close.clicked.connect(self.close)
        
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()
        title_layout.addWidget(btn_close)
        layout.addWidget(title_bar)
        
        # Content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(10)
        
        # Search
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Google Fonts...")
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; color: #d1d1d1; padding: 8px 12px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #e66b2c; }
        """)
        self.search.textChanged.connect(self._filter_fonts)
        content_layout.addWidget(self.search)
        
        # Status
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #4CAF50; font-size: 10px; border: none;")
        self.lbl_status.hide()
        content_layout.addWidget(self.lbl_status)
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setRange(0, 0)  # Indeterminate
        self.progress.setStyleSheet("""
            QProgressBar { border: none; background-color: #1a1a1a; border-radius: 2px; }
            QProgressBar::chunk { background-color: #e66b2c; border-radius: 2px; }
        """)
        self.progress.hide()
        content_layout.addWidget(self.progress)
        
        # Font list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; }
        """)
        
        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(self.list_widget)
        content_layout.addWidget(scroll, stretch=1)
        
        layout.addWidget(content)
        
        # Connect signals
        font_manager.download_progress.connect(self._on_progress)
        font_manager.font_downloaded.connect(self._on_downloaded)
        font_manager.download_failed.connect(self._on_failed)
        
        self._font_widgets = []
        self._populate_fonts()
    
    def _populate_fonts(self):
        catalog = font_manager.get_google_catalog()
        installed = set(font_manager.get_all_fonts())
        
        for name in catalog:
            is_installed = name in installed
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)
            row_layout.setSpacing(8)
            
            lbl = QLabel(name)
            lbl.setStyleSheet("color: #d1d1d1; font-size: 11px; border: none;")
            row_layout.addWidget(lbl, stretch=1)
            
            if is_installed:
                badge = QLabel("✓ Installed")
                badge.setStyleSheet("color: #4CAF50; font-size: 10px; font-weight: bold; border: none;")
                row_layout.addWidget(badge)
            else:
                btn = QPushButton(qta.icon('mdi6.download', color='#e66b2c'), " Download")
                btn.setFixedHeight(24)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet("""
                    QPushButton { background-color: rgba(230, 107, 44, 0.15); color: #e66b2c; 
                        font-size: 10px; font-weight: bold; border: 1px solid rgba(230, 107, 44, 0.3); 
                        border-radius: 4px; padding: 0 8px; }
                    QPushButton:hover { background-color: rgba(230, 107, 44, 0.3); color: #ffffff; }
                    QPushButton:disabled { background-color: rgba(255,255,255,0.05); color: #555; border-color: rgba(255,255,255,0.05); }
                """)
                btn.clicked.connect(lambda checked=False, n=name, b=btn: self._download_font(n, b))
                row_layout.addWidget(btn)
            
            row._font_name = name
            self.list_layout.addWidget(row)
            self._font_widgets.append(row)
    
    def _download_font(self, name, btn):
        btn.setEnabled(False)
        btn.setText(" Downloading...")
        self.progress.show()
        self.lbl_status.show()
        font_manager.download_font(name)
    
    def _on_progress(self, name, status):
        self.lbl_status.setText(f"  {name}: {status}")
        self.lbl_status.show()
    
    def _on_downloaded(self, name):
        self.progress.hide()
        self.lbl_status.setText(f"  ✓ {name} installed successfully!")
        self.lbl_status.setStyleSheet("color: #4CAF50; font-size: 10px; border: none;")
        QTimer.singleShot(3000, self.lbl_status.hide)
        
        # Update the button to show installed
        for widget in self._font_widgets:
            if getattr(widget, '_font_name', '') == name:
                # Clear old layout
                layout = widget.layout()
                while layout.count() > 1:
                    item = layout.takeAt(1)
                    if item.widget():
                        item.widget().deleteLater()
                badge = QLabel("✓ Installed")
                badge.setStyleSheet("color: #4CAF50; font-size: 10px; font-weight: bold; border: none;")
                layout.addWidget(badge)
                break
    
    def _on_failed(self, name, error):
        self.progress.hide()
        self.lbl_status.setText(f"  ✗ {name}: {error}")
        self.lbl_status.setStyleSheet("color: #ff3b30; font-size: 10px; border: none;")
    
    def _filter_fonts(self, text):
        text_lower = text.lower()
        for widget in self._font_widgets:
            name = getattr(widget, '_font_name', '')
            widget.setVisible(text_lower in name.lower() if text_lower else True)


class FontPickerPopup(QFrame):
    """Popup panel for selecting fonts, shown when the font control is clicked."""
    
    font_selected = Signal(str)
    
    def __init__(self, current_font="", parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(280, 400)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        bg_frame = QFrame(self)
        bg_frame.setStyleSheet("""
            QFrame {
                background-color: #151515;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        main_layout.addWidget(bg_frame)
        
        self._current = current_font
        self._font_items = []
        self._current_filter = "all"  # "all", "favorites", "recent"
        
        layout = QVBoxLayout(bg_frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # Search bar
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search fonts...")
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px; color: #d1d1d1; padding: 6px 10px; font-size: 11px;
            }
            QLineEdit:focus { border: 1px solid #e66b2c; }
        """)
        self.search.textChanged.connect(self._filter_fonts)
        layout.addWidget(self.search)
        
        # Filter tabs
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        
        self.tab_buttons = []
        for label, filter_key in [("All", "all"), ("★ Faves", "favorites"), ("Recent", "recent")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent; border: none; color: #808080;
                    font-size: 10px; font-weight: bold; padding: 0 8px;
                    border-bottom: 2px solid transparent;
                }
                QPushButton:hover { color: #ffffff; }
                QPushButton:checked { color: #e66b2c; border-bottom: 2px solid #e66b2c; }
            """)
            btn.clicked.connect(lambda c=False, fk=filter_key: self._set_filter(fk))
            self.tab_buttons.append(btn)
            tab_row.addWidget(btn)
        
        self.tab_buttons[0].setChecked(True)
        
        # Download button
        btn_download = QPushButton(qta.icon('mdi6.download', color='#4299e1'), "")
        btn_download.setFixedSize(24, 24)
        btn_download.setCursor(Qt.PointingHandCursor)
        btn_download.setToolTip("Download Google Fonts")
        btn_download.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background: rgba(66, 153, 225, 0.2); border-radius: 4px; }")
        btn_download.clicked.connect(self._open_download_dialog)
        
        tab_row.addStretch()
        tab_row.addWidget(btn_download)
        layout.addLayout(tab_row)
        
        # Font list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 5px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 2px; }
            QScrollBar::handle:vertical:hover { background: #555; }
        """)
        
        self.list_widget = QWidget()
        self.list_widget.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(1)
        self.list_layout.setAlignment(Qt.AlignTop)
        
        scroll.setWidget(self.list_widget)
        layout.addWidget(scroll, stretch=1)
        
        # Connect to font manager download signals for live refresh
        font_manager.font_downloaded.connect(self._rebuild_list)
        
        self._build_font_list()
    
    def _build_font_list(self):
        # Clear existing
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._font_items.clear()
        
        fonts = self._get_filtered_fonts()
        
        for family in fonts:
            item = FontItemWidget(
                family, 
                is_favorite=font_manager.is_favorite(family),
                is_downloaded=font_manager.is_downloaded(family)
            )
            if family == self._current:
                item.set_selected(True)
            item.clicked.connect(self._on_font_clicked)
            item.favorite_toggled.connect(self._on_fav_toggled)
            self.list_layout.addWidget(item)
            self._font_items.append(item)
    
    def _get_filtered_fonts(self):
        if self._current_filter == "favorites":
            return font_manager.get_favorites()
        elif self._current_filter == "recent":
            return font_manager.get_recent()
        else:
            return font_manager.get_all_fonts()
    
    def _set_filter(self, filter_key):
        self._current_filter = filter_key
        for btn in self.tab_buttons:
            btn.setChecked(False)
        
        idx = {"all": 0, "favorites": 1, "recent": 2}.get(filter_key, 0)
        self.tab_buttons[idx].setChecked(True)
        self._build_font_list()
        self._filter_fonts(self.search.text())
    
    def _filter_fonts(self, text):
        text_lower = text.lower()
        for item in self._font_items:
            item.setVisible(text_lower in item.family_name.lower() if text_lower else True)
    
    def _on_font_clicked(self, family):
        self._current = family
        font_manager.mark_used(family)
        for item in self._font_items:
            item.set_selected(item.family_name == family)
        self.font_selected.emit(family)
        self.close()
    
    def _on_fav_toggled(self, family):
        font_manager.toggle_favorite(family)
        for item in self._font_items:
            if item.family_name == family:
                item.set_favorite(font_manager.is_favorite(family))
                break
        
        # If viewing favorites, rebuild list
        if self._current_filter == "favorites":
            self._build_font_list()
    
    def _open_download_dialog(self):
        self.close()
        dialog = FontDownloadDialog(self.parent())
        dialog.exec()
    
    def _rebuild_list(self, _=None):
        """Called when a font is downloaded to refresh the list."""
        self._build_font_list()


class FontPickerButton(QWidget):
    """The inline font selector widget used in the properties panel.
    Shows current font name in its own face. Click to open popup."""
    
    font_changed = Signal(str)
    
    def __init__(self, current_font="Roboto", parent=None):
        super().__init__(parent)
        self._current_font = current_font
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.btn = QPushButton()
        self.btn.setFixedHeight(28)
        self.btn.setCursor(Qt.PointingHandCursor)
        self._update_button_display()
        
        self.btn.clicked.connect(self._show_popup)
        layout.addWidget(self.btn)
    
    def _update_button_display(self):
        font = QFont(self._current_font, 10)
        self.btn.setFont(font)
        self.btn.setText(f"  {self._current_font}  ▾")
        self.btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(26, 26, 26, 0.8);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1;
                text-align: left; padding: 0 8px;
            }
            QPushButton:hover { border: 1px solid rgba(230, 107, 44, 0.5); }
        """)
    
    def _show_popup(self):
        popup = FontPickerPopup(self._current_font, self)
        popup.font_selected.connect(self._on_font_selected)
        
        # Position below the button
        pos = self.mapToGlobal(self.rect().bottomLeft())
        
        # Prevent going off screen (right side)
        screen_geom = self.screen().availableGeometry()
        if pos.x() + popup.width() > screen_geom.right():
            pos = self.mapToGlobal(self.rect().bottomRight())
            pos.setX(pos.x() - popup.width())
            
        popup.move(pos)
        popup.show()
    
    def _on_font_selected(self, family):
        self._current_font = family
        self._update_button_display()
        self.font_changed.emit(family)
    
    def set_font(self, family):
        """Programmatically set the font without emitting signal."""
        self._current_font = family
        self._update_button_display()
    
    def current_font(self):
        return self._current_font
