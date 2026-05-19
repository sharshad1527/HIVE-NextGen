from PySide6.QtWidgets import QWidget, QRubberBand
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from PySide6.QtGui import QKeyEvent
from ui.workspace_components.draggable_card import DraggableCard
from core.logger import hive_logger as logger

class MediaGridWidget(QWidget):
    """Container widget for media items with rubber-band selection support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()
        self.setFocusPolicy(Qt.StrongFocus) 

    def mousePressEvent(self, event):
        self.setFocus() 
        if event.button() == Qt.LeftButton:
            self.origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.origin, QSize()))
            self.rubber_band.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            self.rubber_band.setGeometry(rect)
            for card in self.findChildren(DraggableCard):
                if card.isVisible():
                    card.is_selected = rect.intersects(card.geometry())
                    card.setStyleSheet(card.selected_style if card.is_selected else card.default_style)
            
    def mouseReleaseEvent(self, event):
        if not self.origin.isNull():
            selected_count = sum(1 for card in self.findChildren(DraggableCard) if card.isVisible() and card.is_selected)
            if selected_count > 0:
                logger.debug(f"MediaGrid: Selection finished, {selected_count} items selected")
        self.rubber_band.hide()
        self.origin = QPoint()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_A and (event.modifiers() & Qt.ControlModifier):
            logger.debug("MediaGrid: Selecting all items")
            for card in self.findChildren(DraggableCard):
                if card.isVisible():
                    card.is_selected = True
                    card.setStyleSheet(card.selected_style)
            event.accept()
        elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
            selected = []
            for card in self.findChildren(DraggableCard):
                if card.isVisible() and card.is_selected:
                    selected.append(card.get_data())
            if selected:
                logger.info(f"MediaGrid: Emitting batch of {len(selected)} items to timeline")
                try:
                    self.parent().parent().parent().parent().add_item_to_timeline.emit({"batch": selected})
                except Exception as e:
                    logger.debug(f"MediaGrid: Failed to emit to timeline: {e}")
            event.accept()
        else:
            super().keyPressEvent(event)
