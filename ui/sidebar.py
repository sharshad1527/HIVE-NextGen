# ui/sidebar.py
import qtawesome as qta
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QToolButton, 
                               QLabel, QSpacerItem, QSizePolicy, QButtonGroup,
                               QApplication, QMenu)
from PySide6.QtGui import QPixmap, QAction
from PySide6.QtCore import Qt, QSize, QEvent, Signal
from utils.paths import get_asset_path
from ui.about_dialog import AboutDialog, ClickableLabel
from ui.logo_animation import HiveLogoAnimation

class Sidebar(QWidget):
    project_hub_requested = Signal()
    new_project_requested = Signal()
    rename_project_requested = Signal()
    export_portable_requested = Signal()

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
        sidebar_layout.setContentsMargins(0, 7, 0, 15) 
        sidebar_layout.setSpacing(10)
        sidebar_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Logo
        self.lbl_logo = HiveLogoAnimation(self)
        self.lbl_logo.setFixedSize(85, 44) 
        self.lbl_logo.start_flow("C")
        sidebar_layout.addWidget(self.lbl_logo, 0, Qt.AlignHCenter)
        self.lbl_logo.clicked.connect(self.show_about_dialog)

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

        self._setup_project_menu()

        # Pushes settings/shortcuts to the bottom
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        sidebar_layout.addItem(spacer)

        # Shortcuts Button
        self.btn_shortcuts = self._create_icon_button("mdi6.keyboard-outline", "Shortcuts", is_tab=False)
        sidebar_layout.addWidget(self.btn_shortcuts, 0, Qt.AlignHCenter)

        # Settings Button
        self.btn_settings = self._create_icon_button("mdi6.cog-outline", "Settings", is_tab=False)
        sidebar_layout.addWidget(self.btn_settings, 0, Qt.AlignHCenter)
        
        layout.addWidget(self.sidebar_box)

        QApplication.instance().installEventFilter(self)

    def _setup_project_menu(self):
        self.project_menu = QMenu(self)
        self.project_menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a1c;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 25px 8px 10px;
                color: #d1d1d1;
                font-size: 11px;
                font-weight: bold;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(230, 107, 44, 0.15);
                color: #e66b2c;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.05);
                margin: 5px 10px;
            }
        """)

        hub_action = QAction(qta.icon('mdi6.home-outline', color='#d1d1d1'), "Return to Hub", self)
        hub_action.triggered.connect(self.project_hub_requested.emit)
        
        new_action = QAction(qta.icon('mdi6.plus-circle-outline', color='#d1d1d1'), "New Project", self)
        new_action.triggered.connect(self.new_project_requested.emit)
        
        rename_action = QAction(qta.icon('mdi6.rename-box-outline', color='#d1d1d1'), "Rename Project", self)
        rename_action.triggered.connect(self.rename_project_requested.emit)
        
        export_action = QAction(qta.icon('mdi6.package-variant-closed', color='#e66b2c'), "Export Portable (.hivezip)", self)
        export_action.triggered.connect(self.export_portable_requested.emit)

        self.project_menu.addAction(hub_action)
        self.project_menu.addAction(new_action)
        self.project_menu.addSeparator()
        self.project_menu.addAction(rename_action)
        self.project_menu.addSeparator()
        self.project_menu.addAction(export_action)

        self.project_menu.aboutToShow.connect(lambda: self.btn_project.setProperty("active_dialog", True) or self.btn_project.style().unpolish(self.btn_project) or self.btn_project.style().polish(self.btn_project))
        self.project_menu.aboutToHide.connect(lambda: self.btn_project.setProperty("active_dialog", False) or self.btn_project.style().unpolish(self.btn_project) or self.btn_project.style().polish(self.btn_project))

        self.btn_project.setMenu(self.project_menu)
        self.btn_project.setPopupMode(QToolButton.InstantPopup)

    def _create_icon_button(self, icon_name, text, checked=False, is_tab=True):
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setText("\n" + text)
        btn.setObjectName("SidebarBtn")
        btn.setIcon(qta.icon(icon_name, color='#808080', color_active='#e66b2c'))
        btn.setIconSize(QSize(22, 22))
        
        if is_tab:
            btn.setCheckable(True)
            btn.setChecked(checked)
            self.btn_group.addButton(btn)
        else:
            btn.setCheckable(False)
            
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
            QToolButton:checked, QToolButton[active_dialog="true"] {
                background-color: rgba(230, 107, 44, 0.1);
                border: 1px solid rgba(230, 107, 44, 0.3);
                color: #e66b2c;
            }
        """)
        
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
    
    def show_about_dialog(self):
        """Create and show the pop-up"""
        self.lbl_logo.start_flow("B")
        dialog = AboutDialog(self)
        dialog.exec()
        # Revert sidebar logo to Idle flow once About is closed
        self.lbl_logo.start_flow("C")
