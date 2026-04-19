# ui/properties.py
import qtawesome as qta
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QWidget, QLineEdit, QComboBox, QSlider, 
                               QScrollArea, QStackedWidget, QSpinBox, QDoubleSpinBox,
                               QColorDialog)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor


from core.signal_hub import global_signals
from core.project_manager import project_manager


class PropertiesPanel(QFrame):
    # Emits item_id, property_name, new_value, save_state(bool)
    property_changed = Signal(str, str, object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.current_item_id = ""
        self.current_item_props = {}
        self.current_sub_type = ""
        self._block_signals = False  # Prevents feedback loops when populating UI
        
        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90); 
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)
        
        self.input_style = """
            QLineEdit {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1; padding: 4px;
            }
            QLineEdit:focus { border: 1px solid #e66b2c; }
        """
        
        self.combo_style = """
            QComboBox {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1; padding: 4px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a; color: #d1d1d1; selection-background-color: #e66b2c;
            }
        """

        self.spinbox_style = """
            QSpinBox, QDoubleSpinBox {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1; padding: 4px; font-family: monospace;
            }
            QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; }
        """

        self.slider_style = """
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #d1d1d1; border: none; height: 10px; width: 10px; margin: -3px 0; border-radius: 5px; }
            QSlider::handle:horizontal:hover { background-color: #ffffff; transform: scale(1.2); }
            QSlider::sub-page:horizontal { background-color: #e66b2c; border-radius: 2px; }
        """

        self.scroll_style = """
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 4px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background: #555; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """
        
        self.btn_primary_style = """
            QPushButton {
                background-color: rgba(230, 107, 44, 0.15); color: #e66b2c; font-size: 11px; font-weight: bold;
                border: 1px solid rgba(230, 107, 44, 0.3); border-radius: 4px; padding: 6px;
            }
            QPushButton:hover { background-color: rgba(230, 107, 44, 0.3); color: #ffffff; }
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        header = QWidget()
        header.setStyleSheet("border-bottom: 1px solid rgba(255, 255, 255, 0.05);")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 10, 15, 10)
        
        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(qta.icon('mdi6.cog-outline', color='#e66b2c').pixmap(14, 14))
        self.lbl_title = QLabel("Properties")
        self.lbl_title.setStyleSheet("color: #d1d1d1; font-size: 12px; font-weight: bold;")
        
        header_layout.addWidget(self.lbl_icon)
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        layout.addWidget(header)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.page_empty = self._create_empty_page()
        self.page_text = self._create_text_page()
        self.page_video = self._create_video_page()
        self.page_image = self._create_image_page()
        self.page_audio = self._create_audio_page()
        self.page_effect = self._create_effect_page()
        
        # New dynamic panels for clip badges
        self.page_transition = self._create_transition_page()
        self.page_clip_effect = self._create_clip_effect_page()

        self.stack.addWidget(self.page_empty)
        self.stack.addWidget(self.page_text)
        self.stack.addWidget(self.page_video)
        self.stack.addWidget(self.page_image)
        self.stack.addWidget(self.page_audio)
        self.stack.addWidget(self.page_effect)
        self.stack.addWidget(self.page_transition)
        self.stack.addWidget(self.page_clip_effect)

        self.show_properties("", "", {})

        global_signals.clip_selected.connect(self.on_clip_selected)
        global_signals.clip_deselected.connect(self.on_clip_deselected)
        
        # Listen for transform changes from the preview player
        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_external_transform)

    def _on_external_transform(self, clip_id, prop_name, value):
        """Called when the preview player moves/rotates a clip — update our sliders without emitting back."""
        if clip_id == self.current_item_id:
            self._block_signals = True
            
            spin_x = getattr(self, 'spin_pos_x', None)
            if self.current_sub_type == "image" and hasattr(self, 'spin_img_pos_x'):
                spin_x = self.spin_img_pos_x
            elif self.current_sub_type == "caption" and hasattr(self, 'spin_cap_pos_x'):
                spin_x = self.spin_cap_pos_x
                
            spin_y = getattr(self, 'spin_pos_y', None)
            if self.current_sub_type == "image" and hasattr(self, 'spin_img_pos_y'):
                spin_y = self.spin_img_pos_y
            elif self.current_sub_type == "caption" and hasattr(self, 'spin_cap_pos_y'):
                spin_y = self.spin_cap_pos_y
                
            slider_rot = getattr(self, 'slider_rotation', None)
            if self.current_sub_type == "image" and hasattr(self, 'slider_img_rotation'):
                slider_rot = self.slider_img_rotation
            elif self.current_sub_type == "caption" and hasattr(self, 'slider_cap_rotation'):
                slider_rot = self.slider_cap_rotation

            if prop_name == "Position_X" and spin_x:
                spin_x.setValue(int(value))
            elif prop_name == "Position_Y" and spin_y:
                spin_y.setValue(int(value))
            elif prop_name == "Rotation" and slider_rot:
                slider_rot.setValue(int(value))
            self._block_signals = False

    def on_clip_selected(self, item_type: str, clip_id: str):
        """Triggered automatically when the Timeline shouts 'clip_selected'."""
        if not project_manager.current_project:
            return
            
        selected_clip = None
        for track in project_manager.current_project.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    selected_clip = clip
                    break
                    
        if selected_clip:
            self.current_track = track.track_id
            self.populate_ui(selected_clip, item_type)

    def on_clip_deselected(self):
        """Triggered when the user clicks the empty background of the timeline."""
        self.clear_ui()

    def populate_ui(self, clip_data, explicit_item_type=None):
        """Reads the clip data and shows the correct property panel with populated values."""
        props = clip_data.applied_effects if isinstance(clip_data.applied_effects, dict) else {}
        item_type = explicit_item_type if explicit_item_type else clip_data.clip_type
        
        if item_type == "caption":
            self.show_properties("caption", clip_data.clip_id, props)
        elif item_type == "video":
            self.show_properties("video", clip_data.clip_id, props)
        elif item_type == "image":
            self.show_properties("image", clip_data.clip_id, props)
        elif item_type == "audio":
            self.show_properties("audio", clip_data.clip_id, props)
        elif item_type == "effect":
            self.show_properties("effect", clip_data.clip_id, props)
        elif item_type in ["transition_in", "transition_out", "clip_effect"]:
            self.show_properties(item_type, clip_data.clip_id, props)
        else:
            self.show_properties("", clip_data.clip_id, props)

    def clear_ui(self):
        """Hides the properties when nothing is selected."""
        self.show_properties("", "", {})

    def show_properties(self, item_type, item_id, item_props):
        self.current_item_id = item_id
        self.current_item_props = item_props
        self.current_sub_type = item_type
        
        type_mapping = {
            'caption':        ("Text Properties", 'mdi6.format-text', self.page_text),
            'video':          ("Video Properties", 'mdi6.movie-open-outline', self.page_video),
            'image':          ("Image Properties", 'mdi6.image-outline', self.page_image),
            'audio':          ("Audio Properties", 'mdi6.volume-high', self.page_audio),
            'effect':         ("Effect Properties", 'mdi6.auto-fix', self.page_effect),
            'transition_in':  ("Transition In", 'mdi6.transition', self.page_transition),
            'transition_out': ("Transition Out", 'mdi6.transition', self.page_transition),
            'clip_effect':    ("Clip Effects", 'mdi6.auto-fix', self.page_clip_effect),
        }

        if item_type in type_mapping:
            title, icon, page = type_mapping[item_type]
            self.lbl_title.setText(title)
            self.lbl_icon.setPixmap(qta.icon(icon, color='#e66b2c').pixmap(14, 14))
            
            self._block_signals = True
            
            # Populate controls from existing clip data
            if item_type == 'caption':
                self.input_text_caption.setText(item_props.get("text", ""))
                self.combo_font.setCurrentText(item_props.get("Font Family", "Roboto"))
                self.slider_font_size.setValue(item_props.get("Font Size", 48))
                self.spin_cap_pos_x.setValue(item_props.get("Position_X", 0))
                self.spin_cap_pos_y.setValue(item_props.get("Position_Y", 0))
                self.slider_cap_scale.setValue(item_props.get("Scale", 100))
                self.slider_cap_rotation.setValue(item_props.get("Rotation", 0))
                self.slider_cap_opacity.setValue(item_props.get("Opacity", 100))
                
            elif item_type == 'video':
                self.spin_pos_x.setValue(item_props.get("Position_X", 0))
                self.spin_pos_y.setValue(item_props.get("Position_Y", 0))
                self.slider_vid_scale.setValue(item_props.get("Scale", 100))
                self.slider_rotation.setValue(item_props.get("Rotation", 0))
                self.slider_vid_opacity.setValue(item_props.get("Opacity", 100))
                self.slider_speed.setValue(item_props.get("Speed", 100))
                self.slider_volume.setValue(item_props.get("Volume", 0))
                
            elif item_type == 'image':
                self.spin_img_pos_x.setValue(item_props.get("Position_X", 0))
                self.spin_img_pos_y.setValue(item_props.get("Position_Y", 0))
                self.slider_img_scale.setValue(item_props.get("Scale", 100))
                self.slider_img_rotation.setValue(item_props.get("Rotation", 0))
                self.slider_img_opacity.setValue(item_props.get("Opacity", 100))
                self.combo_blend.setCurrentText(item_props.get("Blend_Mode", "Normal"))
                self.slider_corner.setValue(item_props.get("Corner_Radius", 0))
                
            elif item_type == 'audio':
                self.slider_aud_vol.setValue(item_props.get("Volume", 0))
                self.slider_pan.setValue(item_props.get("Pan", 0))
                self.slider_fade_in.setValue(item_props.get("Fade_In", 0))
                self.slider_fade_out.setValue(item_props.get("Fade_Out", 0))
                self.slider_aud_speed.setValue(item_props.get("Speed", 100))
                self.slider_pitch.setValue(item_props.get("Pitch", 0))
                
            elif item_type in ['transition_in', 'transition_out']:
                current_trans = item_props.get(item_type, "Cross Dissolve")
                idx = self.combo_transition.findText(current_trans)
                if idx >= 0: self.combo_transition.setCurrentIndex(idx)
                self.slider_trans_dur.setValue(item_props.get(f"{item_type}_duration", 10))
                self.slider_trans_align.setValue(item_props.get(f"{item_type}_alignment", 0))

            elif item_type == 'clip_effect':
                current_effect = item_props.get("primary_effect", "")
                idx = self.combo_clip_effect.findText(current_effect)
                if idx >= 0: self.combo_clip_effect.setCurrentIndex(idx)
                self.slider_effect_speed.setValue(item_props.get("effect_speed", 100))
                self.slider_effect_amount.setValue(item_props.get("effect_amount", 100))
                self.slider_effect_feather.setValue(item_props.get("effect_feather", 0))
            
            self._block_signals = False
            self.stack.setCurrentWidget(page)
        else:
            self.lbl_title.setText("Properties")
            self.lbl_icon.setPixmap(qta.icon('mdi6.cog-outline', color='#e66b2c').pixmap(14, 14))
            self.stack.setCurrentWidget(self.page_empty)

    def _on_prop_change(self, prop_name, new_val, commit=True):
        if self.current_item_id and not self._block_signals:
            self.property_changed.emit(self.current_item_id, prop_name, new_val, commit)

    def _apply_transition_to_all(self):
        if self.current_item_id and self.current_item_props is not None:
            track = getattr(self, "current_track", None)
            if not track: return
            current_trans = self.combo_transition.currentText()
            self.property_changed.emit(
                self.current_item_id, 
                "apply_transition_to_all", 
                {"track": track, "transition": current_trans},
                True
            )

    # --- UI Component Builders ---

    def _add_section(self, layout, title):
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #d1d1d1; font-size: 11px; font-weight: bold; margin-top: 10px; margin-bottom: 2px;")
        layout.addWidget(lbl)

    def _add_slider_row(self, layout, label_text, min_val, max_val, default_val, suffix="", prop_name=None):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()
        
        controls = QWidget()
        controls.setFixedWidth(140)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0,0,0,0)
        controls_layout.setSpacing(8)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.setStyleSheet(self.slider_style)
        
        val_lbl = QLabel(f"{default_val}{suffix}")
        val_lbl.setFixedWidth(30)
        val_lbl.setStyleSheet("color: #d1d1d1; font-size: 10px; font-family: monospace;")
        val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        slider.valueChanged.connect(lambda v, l=val_lbl, s=suffix: l.setText(f"{v}{s}"))
        
        # Wire to property change signal
        if prop_name:
            slider.valueChanged.connect(lambda v, p=prop_name: self._on_prop_change(p, v, commit=False))
            slider.sliderReleased.connect(lambda s=slider, p=prop_name: self._on_prop_change(p, s.value(), commit=True))
        
        controls_layout.addWidget(slider)
        controls_layout.addWidget(val_lbl)
        row.addWidget(controls)
        layout.addLayout(row)
        return slider

    def _add_xy_row(self, layout, label_text, default_x=0, default_y=0, prop_x=None, prop_y=None):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()
        
        controls = QWidget()
        controls.setFixedWidth(140)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0,0,0,0)
        controls_layout.setSpacing(5)

        x_spin = QSpinBox()
        x_spin.setRange(-9999, 9999)
        x_spin.setValue(default_x)
        x_spin.setPrefix("X: ")
        x_spin.setStyleSheet(self.spinbox_style)
        
        y_spin = QSpinBox()
        y_spin.setRange(-9999, 9999)
        y_spin.setValue(default_y)
        y_spin.setPrefix("Y: ")
        y_spin.setStyleSheet(self.spinbox_style)

        # Wire to property change signal
        if prop_x:
            x_spin.valueChanged.connect(lambda v, p=prop_x: self._on_prop_change(p, v, commit=True))
        if prop_y:
            y_spin.valueChanged.connect(lambda v, p=prop_y: self._on_prop_change(p, v, commit=True))

        controls_layout.addWidget(x_spin)
        controls_layout.addWidget(y_spin)
        row.addWidget(controls)
        layout.addLayout(row)
        return x_spin, y_spin

    def _add_combo_row(self, layout, label_text, items, default_index=0, prop_name=None):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()
        
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(default_index)
        combo.setStyleSheet(self.combo_style)
        combo.setFixedWidth(140)
        
        if prop_name:
            combo.currentTextChanged.connect(lambda t, p=prop_name: self._on_prop_change(p, t, commit=True))
        
        row.addWidget(combo)
        layout.addLayout(row)
        return combo

    def _add_color_row(self, layout, label_text, hex_color, prop_name=None):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()
        
        btn_color = QPushButton()
        btn_color.setFixedSize(140, 22)
        btn_color.setStyleSheet(f"""
            QPushButton {{ background-color: {hex_color}; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }}
            QPushButton:hover {{ border: 1px solid #ffffff; }}
        """)
        btn_color.setCursor(Qt.PointingHandCursor)
        btn_color._current_color = hex_color
        
        if prop_name:
            def pick_color(b=btn_color, p=prop_name):
                color = QColorDialog.getColor(QColor(b._current_color), self, "Pick Color")
                if color.isValid():
                    hex_val = color.name()
                    b._current_color = hex_val
                    b.setStyleSheet(f"""
                        QPushButton {{ background-color: {hex_val}; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }}
                        QPushButton:hover {{ border: 1px solid #ffffff; }}
                    """)
                    self._on_prop_change(p, hex_val)
            btn_color.clicked.connect(pick_color)
        
        row.addWidget(btn_color)
        layout.addLayout(row)
        return btn_color

    def _create_scrollable_container(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(self.scroll_style)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(15, 5, 15, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)
        return scroll, layout

    # --- Property Pages ---

    def _create_empty_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        lbl = QLabel("Select an item on the timeline\nto view properties.")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #555555; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl)
        return widget

    def _create_text_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Content")
        self.input_text_caption = QLineEdit("")
        self.input_text_caption.setStyleSheet(self.input_style)
        self.input_text_caption.textChanged.connect(lambda t: self._on_prop_change("text", t, commit=False))
        self.input_text_caption.editingFinished.connect(lambda l=self.input_text_caption: self._on_prop_change("text", l.text(), commit=True))
        layout.addWidget(self.input_text_caption)

        self._add_section(layout, "Typography")
        self.combo_font = self._add_combo_row(layout, "Font Family", ["Roboto", "Arial", "Sour Gummy", "Montserrat", "Inter", "Poppins", "Courier New"], prop_name="Font Family")
        self.slider_font_size = self._add_slider_row(layout, "Font Size", 10, 200, 48, prop_name="Font Size")
        self.btn_text_color = self._add_color_row(layout, "Text Color", "#FFFFFF", prop_name="Text Color")
        self.btn_bg_color = self._add_color_row(layout, "Background", "transparent", prop_name="Bg Color")
        
        self._add_section(layout, "Transform")
        self.spin_cap_pos_x, self.spin_cap_pos_y = self._add_xy_row(layout, "Position", 0, 0, prop_x="Position_X", prop_y="Position_Y")
        self.slider_cap_scale = self._add_slider_row(layout, "Scale", 10, 300, 100, "%", prop_name="Scale")
        self.slider_cap_rotation = self._add_slider_row(layout, "Rotation", -180, 180, 0, "°", prop_name="Rotation")
        self.slider_cap_opacity = self._add_slider_row(layout, "Opacity", 0, 100, 100, "%", prop_name="Opacity")

        return scroll

    def _create_video_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Transform")
        self.spin_pos_x, self.spin_pos_y = self._add_xy_row(layout, "Position", 0, 0, prop_x="Position_X", prop_y="Position_Y")
        self.slider_vid_scale = self._add_slider_row(layout, "Scale", 10, 400, 100, "%", prop_name="Scale")
        self.slider_rotation = self._add_slider_row(layout, "Rotation", -180, 180, 0, "°", prop_name="Rotation")
        self.slider_vid_opacity = self._add_slider_row(layout, "Opacity", 0, 100, 100, "%", prop_name="Opacity")

        self._add_section(layout, "Time & Playback")
        self.slider_speed = self._add_slider_row(layout, "Speed", 10, 500, 100, "%", prop_name="Speed")
        
        self._add_section(layout, "Audio")
        self.slider_volume = self._add_slider_row(layout, "Volume", -60, 12, 0, "dB", prop_name="Volume")

        return scroll

    def _create_image_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Transform")
        self.spin_img_pos_x, self.spin_img_pos_y = self._add_xy_row(layout, "Position", 0, 0, prop_x="Position_X", prop_y="Position_Y")
        self.slider_img_scale = self._add_slider_row(layout, "Scale", 10, 400, 100, "%", prop_name="Scale")
        self.slider_img_rotation = self._add_slider_row(layout, "Rotation", -180, 180, 0, "°", prop_name="Rotation")
        self.slider_img_opacity = self._add_slider_row(layout, "Opacity", 0, 100, 100, "%", prop_name="Opacity")

        self._add_section(layout, "Style")
        self.combo_blend = self._add_combo_row(layout, "Blend Mode", ["Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten"], prop_name="Blend_Mode")
        self.slider_corner = self._add_slider_row(layout, "Corner Radius", 0, 200, 0, "px", prop_name="Corner_Radius")

        return scroll

    def _create_audio_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Mixer")
        self.slider_aud_vol = self._add_slider_row(layout, "Volume", -60, 12, 0, "dB", prop_name="Volume")
        self.slider_pan = self._add_slider_row(layout, "Pan", -100, 100, 0, prop_name="Pan")

        self._add_section(layout, "Fades")
        self.slider_fade_in = self._add_slider_row(layout, "Fade In", 0, 100, 0, "s", prop_name="Fade_In")
        self.slider_fade_out = self._add_slider_row(layout, "Fade Out", 0, 100, 0, "s", prop_name="Fade_Out")
        
        self._add_section(layout, "Time")
        self.slider_aud_speed = self._add_slider_row(layout, "Speed", 10, 400, 100, "%", prop_name="Speed")
        self.slider_pitch = self._add_slider_row(layout, "Pitch", -12, 12, 0, "st", prop_name="Pitch")

        return scroll

    def _create_effect_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Effect Settings")
        self._add_combo_row(layout, "Effect Type", ["Gaussian Blur", "Cinematic Glow", "Color Grade", "Vignette"], prop_name="effect_type")
        
        self._add_section(layout, "Parameters")
        self._add_slider_row(layout, "Intensity", 0, 100, 100, "%", prop_name="intensity")
        self._add_slider_row(layout, "Radius/Spread", 0, 200, 50, "px", prop_name="radius")
        self._add_color_row(layout, "Color Tint", "#e66b2c", prop_name="color_tint")
        
        self._add_section(layout, "Compositing")
        self._add_combo_row(layout, "Blend Mode", ["Normal", "Add", "Screen", "Multiply"], prop_name="blend_mode")
        self._add_slider_row(layout, "Opacity", 0, 100, 100, "%", prop_name="Opacity")

        return scroll

    def _create_transition_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Transition Setting")
        self.combo_transition = self._add_combo_row(layout, "Type", ["Cross Dissolve", "Dip to Black", "Wipe", "Zoom", "Slide", "Glitch"])
        
        # Safely emit properties tied to the current interaction (e.g transition_in vs transition_out)
        self.combo_transition.currentTextChanged.connect(
            lambda t: self._on_prop_change(self.current_sub_type if hasattr(self, 'current_sub_type') else 'transition_in', t)
        )
        
        self._add_section(layout, "Timing")
        self.slider_trans_dur = self._add_slider_row(layout, "Duration", 1, 50, 10, " frames")
        self.slider_trans_dur.valueChanged.connect(
            lambda v: self._on_prop_change(f"{self.current_sub_type}_duration", v)
        )
        
        self.slider_trans_align = self._add_slider_row(layout, "Alignment Center", -100, 100, 0, "%")
        self.slider_trans_align.valueChanged.connect(
            lambda v: self._on_prop_change(f"{self.current_sub_type}_alignment", v)
        )

        self._add_section(layout, "Batch Actions")
        btn_apply_all = QPushButton(qta.icon('mdi6.check-all', color='#e66b2c'), " Apply to All in Track")
        btn_apply_all.setStyleSheet(self.btn_primary_style)
        btn_apply_all.setCursor(Qt.PointingHandCursor)
        btn_apply_all.clicked.connect(self._apply_transition_to_all)
        layout.addWidget(btn_apply_all)

        return scroll

    def _create_clip_effect_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Clip Applied Effect")
        self.combo_clip_effect = self._add_combo_row(layout, "Select Effect", ["Cinematic Glow", "Gaussian Blur", "VHS Retro", "Digital Glitch", "Color Grade", "Vignette"])
        self.combo_clip_effect.currentTextChanged.connect(
            lambda t: self._on_prop_change("primary_effect", t)
        )
        
        self._add_section(layout, "Effect Speed / Timing")
        self.slider_effect_speed = self._add_slider_row(layout, "Playback Speed", 10, 500, 100, "%")
        self.slider_effect_speed.valueChanged.connect(lambda v: self._on_prop_change("effect_speed", v))
        
        self._add_section(layout, "Effect Intensity")
        self.slider_effect_amount = self._add_slider_row(layout, "Amount", 0, 100, 100, "%")
        self.slider_effect_amount.valueChanged.connect(lambda v: self._on_prop_change("effect_amount", v))
        
        self._add_section(layout, "Masking")
        self.slider_effect_feather = self._add_slider_row(layout, "Feather", 0, 100, 0, "px")
        self.slider_effect_feather.valueChanged.connect(lambda v: self._on_prop_change("effect_feather", v))
        
        return scroll