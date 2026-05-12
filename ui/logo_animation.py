import os
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtGui import QSurfaceFormat, QMouseEvent
from utils.paths import get_asset_path

class HiveLogoAnimation(QQuickWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queued_flow = None
        
        # Make the background fully transparent
        self.setClearColor(Qt.transparent)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Ensure hardware acceleration compatibility with high-quality antialiasing
        format = QSurfaceFormat()
        format.setAlphaBufferSize(8)
        format.setSamples(4) # Enable 4x MSAA for smooth edges
        self.setFormat(format)
        
        # Default sizing for sidebar/hub
        self.setFixedSize(85, 44)
        self.setResizeMode(QQuickWidget.SizeRootObjectToView)
        
        # Load the embedded QML
        qml_path = get_asset_path("SplashLogo.qml")
        self.setSource(QUrl.fromLocalFile(qml_path))

        # Connect QML signal to Python signal
        self.statusChanged.connect(self._on_status_changed)

    def _on_status_changed(self, status):
        if status == QQuickWidget.Ready:
            root = self.rootObject()
            if root:
                root.logoClicked.connect(self.clicked.emit)
                if self.queued_flow:
                    root.startFlow(self.queued_flow)
                    self.queued_flow = None

    def start_flow(self, flow_name):
        """Triggers flow A, B, or C in the QML"""
        root = self.rootObject()
        if root:
            root.startFlow(flow_name)
        else:
            self.queued_flow = flow_name

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
