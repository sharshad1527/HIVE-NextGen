# ui/about_dialog.py
import qtawesome as qta
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from utils.paths import get_asset_path

class ClickableLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.setCursor(Qt.PointingHandCursor)
        super().enterEvent(event)

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About H.I.V.E")
        self.setFixedSize(380, 460)

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setup_ui()

    def setup_ui(self):
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Background Frame (to give it your premium dark theme look)
        bg_frame = QFrame()
        bg_frame.setStyleSheet("""
            QFrame {
                background-color: #121214;
                border: 1px solid rgba(230, 107, 44, 0.3); /* Subtle Orange Border */
                border-radius: 15px;
            }
        """)
        frame_layout = QVBoxLayout(bg_frame)
        frame_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        frame_layout.setContentsMargins(30, 40, 30, 30)
        frame_layout.setSpacing(15)

        # 1. Logo
        lbl_logo = QLabel()
        lbl_logo.setAlignment(Qt.AlignCenter)
        lbl_logo.setStyleSheet("border: none; background: transparent;")
        logo_path = get_asset_path("logos", "HIVE_Logo_Mark.svg")
        pixmap = QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        lbl_logo.setPixmap(pixmap)
        frame_layout.addWidget(lbl_logo, 0, Qt.AlignHCenter)

        # 2. App Name
        lbl_title = QLabel("H.I.V.E")
        lbl_title.setStyleSheet("color: #e66b2c; font-size: 24px; font-weight: 900; font-style: italic; border: none;")
        frame_layout.addWidget(lbl_title, 0, Qt.AlignHCenter)

        # 3. Version & Subtitle
        lbl_version = QLabel("Version 0.1.0-alpha")
        lbl_version.setStyleSheet("color: #808080; font-size: 12px; font-weight: bold; border: none;")
        frame_layout.addWidget(lbl_version, 0, Qt.AlignHCenter)
        
        lbl_subtitle = QLabel("Next-Generation Non-Linear Video Editor")
        lbl_subtitle.setStyleSheet("color: #e66b2c; font-size: 13px; font-weight: bold; border: none;")
        frame_layout.addWidget(lbl_subtitle, 0, Qt.AlignHCenter)

        lbl_desc = QLabel(
            "A professional-grade non-linear editing suite engineered for speed and precision. "
            "Featuring seamless proxy workflows, hardware acceleration, and upcoming "
            "AI-driven automation tools designed to revolutionize post-production."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignCenter)
        # Using a slightly darker text for the description to create a visual hierarchy
        lbl_desc.setStyleSheet("color: #a0a0a0; font-size: 12px; border: none; margin-top: 5px; line-height: 1.2;")
        frame_layout.addWidget(lbl_desc, 0, Qt.AlignHCenter)

        # Divider line
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1); border: none;")
        frame_layout.addWidget(divider)

        # 4. Credits
        lbl_credit = QLabel("Developed by Harshad")
        lbl_credit.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold; border: none;")
        frame_layout.addWidget(lbl_credit, 0, Qt.AlignHCenter)

        frame_layout.addStretch()

        # 5. Buttons (GitHub & Close)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_github = QPushButton(qta.icon('mdi6.github', color='#ffffff'), " GitHub")
        btn_github.setFixedHeight(36)
        btn_github.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }
        """)
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/sharshad1527/HIVE-NewGen")))

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(230, 107, 44, 0.1);
                border: 1px solid rgba(230, 107, 44, 0.5);
                border-radius: 8px;
                color: #e66b2c;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(230, 107, 44, 0.2); }
        """)
        btn_close.clicked.connect(self.accept) # Closes the dialog

        btn_layout.addWidget(btn_github)
        btn_layout.addWidget(btn_close)
        
        frame_layout.addLayout(btn_layout)
        layout.addWidget(bg_frame)