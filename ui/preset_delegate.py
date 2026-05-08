import qtawesome as qta
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QApplication
from PySide6.QtCore import Qt, QRect, QSize, QPoint, Signal, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush
import os
from core.cloud_client import cloud_client

class PresetDelegate(QStyledItemDelegate):
    """
    Custom delegate to render CapCut-style preset cards.
    Supports local/cloud states and interactive buttons.
    """
    add_requested = Signal(int) # row index
    download_requested = Signal(int) # row index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.card_size = QSize(145, 120)
        self.thumb_size = QSize(125, 70) # Reduced for better margins
        self._thumb_cache = {} # path -> QPixmap

    def paint(self, painter, option, index):
        import time
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Get Data
        name = index.data(Qt.UserRole + 1) # NameRole
        icon_name = index.data(Qt.UserRole + 2) # IconRole
        thumb_path = index.data(Qt.UserRole + 6) # ThumbRole
        state = index.data(Qt.UserRole + 8) # DownloadStateRole
        item_id = index.data(Qt.UserRole + 9) # IDRole
        
        # Adjust rect for margins
        rect = option.rect.adjusted(5, 5, -5, -5)
        
        # 2. Draw Glow Effect if recently downloaded
        model = index.model()
        if hasattr(model, "sourceModel"):
            source_model = model.sourceModel()
            download_time = source_model.get_download_time(item_id) if hasattr(source_model, "get_download_time") else 0
        else:
            download_time = model.get_download_time(item_id) if hasattr(model, "get_download_time") else 0

        if download_time > 0 and (time.time() - download_time) < 3.0:
            glow_rect = rect.adjusted(-2, -2, 2, 2)
            painter.setPen(QPen(QColor(230, 107, 44, 200), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(glow_rect, 10, 10)

        # 3. Draw Background
        is_selected = option.state & QStyle.State_Selected
        is_hovered = option.state & QStyle.State_MouseOver
        
        bg_color = QColor(26, 26, 26, 153)
        border_color = QColor(255, 255, 255, 13)
        if is_selected:
            border_color = QColor("#e66b2c")
        elif is_hovered:
            border_color = QColor(230, 107, 44, 128)
            
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 2 if is_selected else 1))
        painter.drawRoundedRect(rect, 8, 8)

        # 4. Draw Thumbnail (Strict containment)
        # Center horizontally
        thumb_x = rect.left() + (rect.width() - self.thumb_size.width()) // 2
        thumb_rect = QRect(thumb_x, rect.top() + 7, self.thumb_size.width(), self.thumb_size.height())
        
        painter.setBrush(QBrush(QColor("#0a0a0a")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(thumb_rect, 4, 4)
        
        pixmap = None
        if thumb_path:
            if not os.path.isabs(thumb_path):
                cloud_thumb = cloud_client.cache_dir / thumb_path
                if cloud_thumb.exists():
                    thumb_path = str(cloud_thumb)

            if os.path.exists(thumb_path):
                if thumb_path in self._thumb_cache:
                    pixmap = self._thumb_cache[thumb_path]
                else:
                    pixmap = QPixmap(thumb_path)
                    if not pixmap.isNull():
                        # Scale to fit inside
                        pixmap = pixmap.scaled(self.thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self._thumb_cache[thumb_path] = pixmap
        
        if pixmap and not pixmap.isNull():
            painter.save()
            from PySide6.QtGui import QPainterPath
            path = QPainterPath()
            path.addRoundedRect(thumb_rect, 4, 4)
            painter.setClipPath(path)
            
            # Center the pixmap inside the thumb_rect
            target_rect = QStyle.alignedRect(Qt.LeftToRight, Qt.AlignCenter, pixmap.size(), thumb_rect)
            painter.drawPixmap(target_rect, pixmap)
            painter.restore()
        else:
            icon = qta.icon(icon_name, color='#a0a0a0')
            icon_pixmap = icon.pixmap(24, 24)
            icon_rect = QStyle.alignedRect(Qt.LeftToRight, Qt.AlignCenter, icon_pixmap.size(), thumb_rect)
            painter.drawPixmap(icon_rect, icon_pixmap)

        # 5. Draw Title
        title_rect = QRect(rect.left() + 5, thumb_rect.bottom() + 5, rect.width() - 10, 20)
        painter.setPen(QColor("#d1d1d1"))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(name, Qt.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignCenter, elided_title)

        # 6. Overlays
        if state == 1: # STATE_CLOUD
            cloud_pixmap = qta.icon('mdi6.cloud-download-outline', color="#ffffff").pixmap(18, 18)
            painter.drawPixmap(rect.left() + 8, rect.top() + 8, cloud_pixmap)
        elif state == 2: # STATE_DOWNLOADING
            painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(thumb_rect, 4, 4)
            painter.setPen(QColor("#e66b2c"))
            painter.drawText(thumb_rect, Qt.AlignCenter, "...")

        # 7. Add Button
        if state == 0: # LOCAL
            btn_rect = QRect(rect.right() - 25, rect.top() + 5, 22, 22)
            painter.setBrush(QBrush(QColor(230, 107, 44, 204)))
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawEllipse(btn_rect)
            plus_icon = qta.icon('mdi6.plus', color="#ffffff")
            painter.drawPixmap(btn_rect.adjusted(4,4,-4,-4), plus_icon.pixmap(14, 14))

        painter.restore()

    def sizeHint(self, option, index):
        return self.card_size

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease:
            rect = option.rect.adjusted(5, 5, -5, -5)
            btn_rect = QRect(rect.right() - 25, rect.top() + 5, 22, 22)
            
            click_pos = event.position().toPoint()
            if btn_rect.contains(click_pos):
                state = index.data(Qt.UserRole + 8)
                if state == 0: # LOCAL
                    self.add_requested.emit(index.row())
                    return True
            
            # Clicking anywhere on a cloud item triggers download
            state = index.data(Qt.UserRole + 8)
            if state == 1: # CLOUD
                self.download_requested.emit(index.row())
                return True
                
        return False
