# ui/sidebar.py
import qtawesome as qta
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QToolButton, 
                               QLabel, QSpacerItem, QSizePolicy, QButtonGroup,
                               QApplication)
from PySide6.QtCore import Qt, QSize, QEvent

class Sidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarContainer")
        self.setFixedWidth(85) # Increased width to prevent text cut-off
        
        # Main layout for the left column
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # --- Unified Sidebar Box ---
        self.sidebar_box = QFrame()
        self.sidebar_box.setStyleSheet("""
            QFrame {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        sidebar_layout = QVBoxLayout(self.sidebar_box)
        sidebar_layout.setContentsMargins(0, 0, 0, 15) 
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Logo
        self.lbl_logo = QLabel("H.")
        self.lbl_logo.setFixedSize(85, 44) 
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        self.lbl_logo.setStyleSheet("color: #e66b2c; font-size: 20px; font-weight: 900; font-style: italic; background: transparent; border: none;")
        sidebar_layout.addWidget(self.lbl_logo, 0, Qt.AlignHCenter)

        # Button Group for exclusive selection
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True) 

        # Tool Buttons
        self.btn_project = self._create_icon_button("mdi6.folder-outline", "Project", True)
        self.btn_assets = self._create_icon_button("mdi6.layers-outline", "Assets")
        self.btn_export = self._create_icon_button("mdi6.export-variant", "Export")
        
        sidebar_layout.addWidget(self.btn_project, 0, Qt.AlignHCenter)
        sidebar_layout.addWidget(self.btn_assets, 0, Qt.AlignHCenter)
        sidebar_layout.addWidget(self.btn_export, 0, Qt.AlignHCenter)

        # Pushes settings/shortcuts to the bottom
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        sidebar_layout.addItem(spacer)

        # Shortcuts Button
        self.btn_shortcuts = self._create_icon_button("mdi6.keyboard-outline", "Shortcuts")
        sidebar_layout.addWidget(self.btn_shortcuts, 0, Qt.AlignHCenter)

        # Settings Button
        self.btn_settings = self._create_icon_button("mdi6.cog-outline", "Settings")
        sidebar_layout.addWidget(self.btn_settings, 0, Qt.AlignHCenter)
        
        layout.addWidget(self.sidebar_box)

        QApplication.instance().installEventFilter(self)

    def _create_icon_button(self, icon_name, text, checked=False):
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setText("\n" + text)
        btn.setObjectName("SidebarBtn")
        btn.setIcon(qta.icon(icon_name, color='#808080', color_active='#e66b2c'))
        btn.setIconSize(QSize(22, 22))
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(70, 60)
        
        btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                color: #808080;
                font-size: 10px;
                font-weight: 600;
                padding-top: 6px;
                padding-bottom: 4px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.05);
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: rgba(230, 107, 44, 0.1);
                border: 1px solid rgba(230, 107, 44, 0.3);
                color: #e66b2c;
            }
        """)
        
        self.btn_group.addButton(btn)
        return btn

    def clear_selection(self):
        # Allow clearing by temporarily disabling exclusivity
        if self.btn_group.checkedButton():
            self.btn_group.setExclusive(False)
            self.btn_group.checkedButton().setChecked(False)
            self.btn_group.setExclusive(True)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if hasattr(event, 'globalPosition'):
                global_pos = event.globalPosition().toPoint()
                local_pos = self.mapFromGlobal(global_pos)
                if not self.rect().contains(local_pos):
                    # For a strict radio-group, we usually don't deselect when clicking away
                    pass
        return super().eventFilter(obj, event)