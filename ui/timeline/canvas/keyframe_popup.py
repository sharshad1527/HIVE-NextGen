from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Qt
import qtawesome as qta

from core.signal_hub import global_signals
try:
    from core.models import Easing
except ImportError:
    Easing = None


class KeyframePopup(QWidget):
    def __init__(self, item, backend_clip, hit_kfs, canvas, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.item = item
        self.backend_clip = backend_clip
        self.hit_kfs = hit_kfs
        self.canvas = canvas
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        self.setStyleSheet("""
            QWidget { background-color: #1a1a1a; border: 1px solid #333333; border-radius: 6px; }
            QPushButton { background-color: transparent; border: none; color: white; padding: 5px; font-size: 11px; }
            QPushButton:hover { background-color: #333333; border-radius: 4px; }
            QLabel { color: #888888; font-size: 10px; font-weight: bold; border: none; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        title = ", ".join([prop.replace('_', ' ').title() for prop, kf in hit_kfs])
        if len(hit_kfs) > 2: title = f"{len(hit_kfs)} Keyframes"
        else: title += " Keyframe" + ("s" if len(hit_kfs) > 1 else "")
            
        lbl = QLabel(title)
        layout.addWidget(lbl)
        
        # Presets grid
        grid = QGridLayout()
        grid.setSpacing(2)
        
        presets = [
            ("Linear", Easing.LINEAR if Easing else 0, "mdi6.vector-line"),
            ("Ease In", Easing.EASE_IN if Easing else 1, "mdi6.transition"),
            ("Ease Out", Easing.EASE_OUT if Easing else 2, "mdi6.transition"),
            ("Ease In-Out", Easing.EASE_IN_OUT if Easing else 3, "mdi6.transition"),
            ("Bounce", Easing.BOUNCE if Easing else 4, "mdi6.chart-bell-curve-cumulative"),
            ("Elastic", Easing.ELASTIC if Easing else 5, "mdi6.chart-bell-curve-cumulative"),
            ("Cubic In", Easing.CUBIC_IN if Easing else 6, "mdi6.chart-bell-curve-cumulative"),
            ("Cubic Out", Easing.CUBIC_OUT if Easing else 7, "mdi6.chart-bell-curve-cumulative")
        ]
        
        row, col = 0, 0
        for name, enum_val, icon_name in presets:
            btn = QPushButton(name)
            btn.setIcon(qta.icon(icon_name, color="white"))
            btn.clicked.connect(lambda checked, e=enum_val: self.apply_easing(e))
            grid.addWidget(btn, row, col)
            col += 1
            if col > 1:
                col = 0
                row += 1
                
        layout.addLayout(grid)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #333333; border: none;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        
        btn_graph = QPushButton("Open Graph Editor")
        btn_graph.setIcon(qta.icon("mdi6.chart-timeline-variant", color="#e66b2c"))
        btn_graph.setStyleSheet("color: #e66b2c;")
        btn_graph.clicked.connect(self.open_graph)
        layout.addWidget(btn_graph)
        
        btn_del = QPushButton("Delete Keyframe")
        btn_del.setIcon(qta.icon("mdi6.delete-outline", color="#ff4444"))
        btn_del.setStyleSheet("color: #ff4444;")
        btn_del.clicked.connect(self.delete_keyframe)
        layout.addWidget(btn_del)

    def apply_easing(self, easing_val):
        for prop_name, kf in self.hit_kfs:
            kf.easing = easing_val
        self._refresh()
        self.close()
        
    def open_graph(self):
        from ui.timeline.graph_editor import GraphEditorDialog
        dialog = GraphEditorDialog(self.item, self.backend_clip, self.hit_kfs, self.canvas)
        dialog.exec()
        self.close()
        
    def delete_keyframe(self):
        for prop_name, kf in self.hit_kfs:
            anim_track = self.backend_clip.animations[prop_name]
            if hasattr(anim_track, 'remove_keyframe'):
                anim_track.remove_keyframe(kf.time)
            else:
                if kf in anim_track.keyframes:
                    anim_track.keyframes.remove(kf)
            
            if not anim_track.keyframes:
                anim_track.enabled = False
        self._refresh()
        self.close()

    def _refresh(self):
        if hasattr(global_signals, 'clip_updated'): global_signals.clip_updated.emit(self.backend_clip)
        if hasattr(global_signals, 'force_refresh'): global_signals.force_refresh.emit()
        self.canvas.update()
