# ui/timeline/timeline_panel.py
import qtawesome as qta
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget, QScrollArea, QSlider
from PySide6.QtCore import Qt, QTimer

from core.signal_hub import global_signals
from core.models import ProjectData
from core.project_manager import project_manager

# Import the detached canvas component
from .timeline_canvas import TracksCanvas
from ui.crop_dialog import CropDialog


class TimelinePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("border-bottom: 1px solid #1f1f1f; background-color: #111111; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        tool_layout = QHBoxLayout(toolbar)
        tool_layout.setContentsMargins(15, 0, 15, 0)
        tool_layout.setSpacing(4)

        self.btn_pointer = self._create_tool_btn('mdi6.cursor-default-outline', True, "Select Tool (V)")
        self.btn_blade = self._create_tool_btn('mdi6.content-cut', False, "Blade Tool (C)")
        sep1 = self._create_separator()
        self.btn_undo = self._create_tool_btn('mdi6.undo', False, "Undo (Ctrl+Z)")
        self.btn_redo = self._create_tool_btn('mdi6.redo', False, "Redo (Ctrl+Shift+Z)")
        sep2 = self._create_separator()
        self.btn_split = self._create_tool_btn('mdi6.content-cut', False, "Split at Playhead (Ctrl+B)")
        self.btn_trim_left = self._create_tool_btn('mdi6.arrow-left-box', False, "Trim Left (Q)")
        self.btn_trim_right = self._create_tool_btn('mdi6.arrow-right-box', False, "Trim Right (W)")
        self.btn_trash = self._create_tool_btn('mdi6.trash-can-outline', False, "Delete Selected (Del)")
        sep3 = self._create_separator()
        self.btn_freeze = self._create_tool_btn('mdi6.snowflake', False, "Freeze Frame (Shift+F)")
        self.btn_reverse = self._create_tool_btn('mdi6.history', False, "Reverse (Ctrl+R)")
        self.btn_mirror = self._create_tool_btn('mdi6.swap-horizontal', False, "Mirror (Alt+M)")
        self.btn_rotate = self._create_tool_btn('mdi6.rotate-right', False, "Rotate (Alt+R)")
        self.btn_crop = self._create_tool_btn('mdi6.crop', False, "Crop Media (Alt+C)")

        for w in [self.btn_pointer, self.btn_blade, sep1, self.btn_undo, self.btn_redo, sep2, 
                  self.btn_split, self.btn_trim_left, self.btn_trim_right, self.btn_trash, sep3,
                  self.btn_freeze, self.btn_reverse, self.btn_mirror, self.btn_rotate, self.btn_crop]:
            tool_layout.addWidget(w)
        tool_layout.addStretch()

        self.btn_magnet = self._create_tool_btn('mdi6.magnet', True, "Toggle Snapping (S)")
        self.btn_gravity = self._create_tool_btn('mdi6.arrow-collapse-vertical', True, "Toggle V1 Gravity (G)")
        sep4 = self._create_separator()
        self.btn_zoom_out = self._create_tool_btn('mdi6.magnify-minus-outline', False)
        self.slider_zoom = QSlider(Qt.Horizontal)
        self.slider_zoom.setRange(1, 1000) 
        self.slider_zoom.setValue(100)
        self.slider_zoom.setFixedWidth(100)
        self.slider_zoom.setStyleSheet("""
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #d1d1d1; border: none; height: 10px; width: 10px; margin: -3px 0; border-radius: 5px; }
            QSlider::sub-page:horizontal { background-color: #e66b2c; border-radius: 2px; }
        """)
        self.btn_zoom_in = self._create_tool_btn('mdi6.magnify-plus-outline', False)

        for w in [self.btn_magnet, self.btn_gravity, sep4, self.btn_zoom_out, self.slider_zoom, self.btn_zoom_in]:
            tool_layout.addWidget(w)
        
        main_layout.addWidget(toolbar)

        split_area = QHBoxLayout()
        split_area.setContentsMargins(0, 0, 0, 0)
        split_area.setSpacing(0)

        self.headers_scroll = QScrollArea()
        self.headers_scroll.setWidgetResizable(True)
        self.headers_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.headers_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.headers_scroll.setStyleSheet("border: none; background-color: #151515;")
        self.headers_scroll.setFixedWidth(180)

        self.headers_widget = QWidget()
        self.headers_widget.setFixedWidth(180)
        self.headers_layout = QVBoxLayout(self.headers_widget)
        self.headers_layout.setContentsMargins(0, 0, 0, 0)
        self.headers_layout.setSpacing(0)
        self.headers_scroll.setWidget(self.headers_widget)
        
        split_area.addWidget(self.headers_scroll)

        self.tracks_scroll = QScrollArea()
        self.tracks_scroll.setWidgetResizable(True)
        self.tracks_scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: #111111; border-bottom-right-radius: 12px; }
            QScrollBar:horizontal { background: #131313; height: 12px; }
            QScrollBar::handle:horizontal { background: #333; border-radius: 6px; }
            QScrollBar::handle:horizontal:hover { background: #555; }
            QScrollBar:vertical { background: #131313; width: 12px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 6px; }
            QScrollBar::handle:vertical:hover { background: #555; }
        """)
        
        self.tracks_canvas = TracksCanvas()
        
        self.tracks_canvas.scroll_requested.connect(self._auto_scroll_timeline)
        self.tracks_canvas.v_scroll_requested.connect(self._auto_v_scroll_timeline)
        self.tracks_canvas.zoom_requested.connect(self._auto_zoom_timeline)
        
        self.tracks_canvas.tracks_changed.connect(self._rebuild_headers)
        self.tracks_canvas.item_clicked.connect(self._on_item_selected)
        
        self.tracks_scroll.setWidget(self.tracks_canvas)
        split_area.addWidget(self.tracks_scroll)
        
        self.tracks_scroll.verticalScrollBar().valueChanged.connect(self.headers_scroll.verticalScrollBar().setValue)
        self.headers_scroll.verticalScrollBar().valueChanged.connect(self.tracks_scroll.verticalScrollBar().setValue)
        
        self.tracks_scroll.verticalScrollBar().valueChanged.connect(self.tracks_canvas.set_v_scroll)

        main_layout.addLayout(split_area)
        self._rebuild_headers()

        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_pointer.clicked.connect(lambda: self._set_tool("pointer"))
        self.btn_blade.clicked.connect(lambda: self._set_tool("blade"))
        self.btn_magnet.clicked.connect(self._toggle_magnet)
        self.btn_gravity.clicked.connect(self._toggle_gravity)
        self.btn_undo.clicked.connect(self.tracks_canvas.undo)
        self.btn_redo.clicked.connect(self.tracks_canvas.redo)
        self.btn_split.clicked.connect(self.tracks_canvas.split_at_playhead)
        self.btn_trim_left.clicked.connect(self.tracks_canvas.trim_left)
        self.btn_trim_right.clicked.connect(self.tracks_canvas.trim_right)
        self.btn_trash.clicked.connect(self.tracks_canvas.delete_selected_item)
        self.btn_freeze.clicked.connect(self.tracks_canvas.freeze_frame_at_playhead)
        self.btn_reverse.clicked.connect(lambda: self.tracks_canvas.toggle_item_property("reverse"))
        self.btn_mirror.clicked.connect(lambda: self.tracks_canvas.toggle_item_property("mirror"))
        self.btn_rotate.clicked.connect(lambda: self.tracks_canvas.toggle_item_property("rotate"))
        self.btn_crop.clicked.connect(self._open_crop_dialog)

        global_signals.project_loaded.connect(self.on_project_loaded)
        
        if project_manager.current_project:
            QTimer.singleShot(0, lambda: self.on_project_loaded(project_manager.current_project))

    def _open_crop_dialog(self):
        selected_ids = list(self.tracks_canvas.selected_ids)
        if not selected_ids: return
        dialog = CropDialog(self.tracks_canvas, selected_ids[0], self)
        dialog.exec()

    def on_project_loaded(self, project_data: ProjectData):
        """Passes the backend project data down to the canvas to be drawn."""
        print(f"TIMELINE: Parsing project '{project_data.name}'...")
        self.tracks_canvas.load_from_project(project_data)
        self.tracks_canvas.sync_to_project()

    def _zoom_out(self):
        val = self.slider_zoom.value()
        step = 5 if val <= 30 else (10 if val <= 100 else 50)
        self.slider_zoom.setValue(max(1, val - step))

    def _zoom_in(self):
        val = self.slider_zoom.value()
        step = 5 if val < 30 else (10 if val < 100 else 50)
        self.slider_zoom.setValue(min(1000, val + step))

    def step_playhead_forward(self):
        current_frame = round(self.tracks_canvas.logical_playhead / (100 / 30.0))
        z = self.tracks_canvas.zoom_factor
        if z >= 3.0: frames_to_add = 1
        elif z >= 1.0: frames_to_add = 5
        else: frames_to_add = 30
        new_frame = current_frame + frames_to_add
        new_pos = (new_frame * 100 / 30.0) + 0.05
        self.tracks_canvas.set_playhead(new_pos)

    def step_playhead_backward(self):
        current_frame = round(self.tracks_canvas.logical_playhead / (100 / 30.0))
        z = self.tracks_canvas.zoom_factor
        if z >= 3.0: frames_to_sub = 1
        elif z >= 1.0: frames_to_sub = 5
        else: frames_to_sub = 30
        new_frame = max(0, current_frame - frames_to_sub)
        new_pos = (new_frame * 100 / 30.0) + 0.05 if new_frame > 0 else 0.0
        self.tracks_canvas.set_playhead(new_pos)

    def _create_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #333333; margin: 5px 2px;")
        return sep

    def _set_tool(self, tool_name):
        self.tracks_canvas.active_tool = tool_name
        self._update_btn_visuals(self.btn_pointer, tool_name == "pointer")
        self._update_btn_visuals(self.btn_blade, tool_name == "blade")
        self.tracks_canvas.setCursor(Qt.ArrowCursor if tool_name == "pointer" else Qt.CrossCursor)
        if tool_name != "blade":
            self.tracks_canvas.blade_line_x = None
            self.tracks_canvas.update()

    def _toggle_magnet(self):
        state = not self.tracks_canvas.magnet_enabled
        self.tracks_canvas.magnet_enabled = state
        self._update_btn_visuals(self.btn_magnet, state)

    def _toggle_gravity(self):
        state = not self.tracks_canvas.v1_gravity_enabled
        self.tracks_canvas.v1_gravity_enabled = state
        self._update_btn_visuals(self.btn_gravity, state)
        if state:
            self.tracks_canvas._apply_magnetic_v1()
            self.tracks_canvas.update_max_width()
            self.tracks_canvas.update()

    def _toggle_track_state(self, track_id, state_type):
        self.tracks_canvas.toggle_track_state(track_id, state_type)
        self._rebuild_headers()

    def _on_item_selected(self, item_type, item_id, item_props):
        has_selection = bool(item_type) and item_type not in ["transition_in", "transition_out", "clip_effect"]
        self._update_btn_visuals(self.btn_trash, has_selection)
        self._update_btn_visuals(self.btn_split, has_selection)
        self._update_btn_visuals(self.btn_trim_left, has_selection)
        self._update_btn_visuals(self.btn_trim_right, has_selection)
        has_video = item_type in ["video", "image", "multiple"]
        self._update_btn_visuals(self.btn_freeze, has_video and item_type == "video")
        self._update_btn_visuals(self.btn_reverse, has_video)
        self._update_btn_visuals(self.btn_mirror, has_video)
        self._update_btn_visuals(self.btn_rotate, has_video)
        self._update_btn_visuals(self.btn_crop, has_video)

    def _update_btn_visuals(self, btn, is_active):
        icon_name = btn.property("icon_name")
        color = '#e66b2c' if is_active else '#808080'
        btn.setIcon(qta.icon(icon_name, color=color))
        bg_color = "rgba(230, 107, 44, 0.2)" if is_active else "transparent"
        border = "1px solid rgba(230, 107, 44, 0.5)" if is_active else "1px solid transparent"
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; border: {border}; border-radius: 4px; }}
            QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.1); }}
        """)

    def _create_tool_btn(self, icon_name, is_active, tooltip=""):
        btn = QPushButton()
        btn.setFixedSize(28, 28)
        if tooltip: btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("icon_name", icon_name)
        self._update_btn_visuals(btn, is_active)
        return btn

    def _rebuild_headers(self):
        while self.headers_layout.count():
            child = self.headers_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        spacer = QWidget()
        spacer.setFixedHeight(32)
        spacer.setStyleSheet("background-color: transparent;")
        self.headers_layout.addWidget(spacer)
        
        for t in self.tracks_canvas.track_defs:
            state = self.tracks_canvas.track_states.get(t["id"], {"locked": False, "hidden": False})
            self.headers_layout.addWidget(
                self._create_header(
                    t["label"], t["icon"], t["height"], 
                    active=(t["group"]=="caption"), 
                    track_id=t["id"],
                    locked=state["locked"],
                    hidden=state["hidden"],
                    group=t["group"]
                )
            )
            
        self.headers_widget.setFixedHeight(self.tracks_canvas.height())
        
        if not hasattr(self, 'floating_seq_header'):
            self.floating_seq_header = self._create_header("Sequence 1", "", 32, is_title=True)
            self.floating_seq_header.setParent(self)
            self.floating_seq_header.show()
            
        self.floating_seq_header.setGeometry(0, 40, 180, 32)
        self.floating_seq_header.raise_()

    def _auto_scroll_timeline(self, dx):
        sb = self.tracks_scroll.horizontalScrollBar()
        sb.setValue(sb.value() + dx)

    def _auto_v_scroll_timeline(self, dy):
        sb = self.tracks_scroll.verticalScrollBar()
        sb.setValue(sb.value() + dy)
        
    def _auto_zoom_timeline(self, delta):
        if delta > 0: self._zoom_in()
        else: self._zoom_out()

    def _on_zoom_changed(self, value):
        new_zoom = value / 100.0
        playhead_logical = self.tracks_canvas.logical_playhead
        self.tracks_canvas.set_zoom(new_zoom)
        def adjust_scroll():
            playhead_physical_x = int(playhead_logical * new_zoom)
            viewport_w = self.tracks_scroll.viewport().width()
            target_scroll_x = playhead_physical_x - (viewport_w // 2)
            self.tracks_scroll.horizontalScrollBar().setValue(max(0, target_scroll_x))
        QTimer.singleShot(0, adjust_scroll)

    def _create_header(self, text, icon_name, height, is_title=False, active=False, track_id=None, locked=False, hidden=False, group=""):
        header = QWidget()
        header.setFixedHeight(height)
        border_color = "#1f1f1f"
        bg_color = "#131313" if is_title else "transparent"
        header.setStyleSheet(f"border-bottom: 1px solid {border_color}; background-color: {bg_color};")
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(8)
        
        if is_title:
            lbl = QLabel(text.upper())
            lbl.setStyleSheet("color: #555555; font-size: 10px; font-weight: bold; border: none; letter-spacing: 1px;")
            layout.addWidget(lbl)
        else:
            icon_lbl = QLabel()
            icon_color = '#e66b2c' if active else '#808080'
            icon_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(14, 14))
            icon_lbl.setStyleSheet("border: none;")
            
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #d1d1d1; font-size: 11px; font-weight: bold; border: none;")
            
            layout.addWidget(icon_lbl)
            layout.addWidget(lbl)
            layout.addStretch()

            if track_id not in ["video_1", "audio_1", "word_1"]:
                btn_up = QPushButton()
                btn_up.setIcon(qta.icon('mdi6.chevron-up', color='#555555'))
                btn_up.setFixedSize(16, 20)
                btn_up.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(255,255,255,0.1); border-radius: 4px; }")
                btn_up.setCursor(Qt.PointingHandCursor)
                btn_up.clicked.connect(lambda _, t_id=track_id: self.tracks_canvas.move_track_up(t_id))
                
                btn_down = QPushButton()
                btn_down.setIcon(qta.icon('mdi6.chevron-down', color='#555555'))
                btn_down.setFixedSize(16, 20)
                btn_down.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: rgba(255,255,255,0.1); border-radius: 4px; }")
                btn_down.setCursor(Qt.PointingHandCursor)
                btn_down.clicked.connect(lambda _, t_id=track_id: self.tracks_canvas.move_track_down(t_id))
                
                layout.addWidget(btn_up)
                layout.addWidget(btn_down)

            if group != "word":
                btn_hide = QPushButton()
                btn_hide.setIcon(qta.icon('mdi6.eye-off-outline' if hidden else 'mdi6.eye-outline', color='#e66b2c' if hidden else '#555555'))
                btn_hide.setFixedSize(20, 20)
                btn_hide.setStyleSheet("background: transparent; border: none;")
                btn_hide.setCursor(Qt.PointingHandCursor)
                btn_hide.setToolTip("Hide Track" if not hidden else "Show Track")
                btn_hide.clicked.connect(lambda _, t_id=track_id: self._toggle_track_state(t_id, "hidden"))
    
                btn_lock = QPushButton()
                btn_lock.setIcon(qta.icon('mdi6.lock-outline' if locked else 'mdi6.lock-open-variant-outline', color='#e66b2c' if locked else '#555555'))
                btn_lock.setFixedSize(20, 20)
                btn_lock.setStyleSheet("background: transparent; border: none;")
                btn_lock.setCursor(Qt.PointingHandCursor)
                btn_lock.setToolTip("Unlock Track" if locked else "Lock Track")
                btn_lock.clicked.connect(lambda _, t_id=track_id: self._toggle_track_state(t_id, "locked"))
    
                layout.addWidget(btn_hide)
                layout.addWidget(btn_lock)
            
        return header