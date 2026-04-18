# ui/properties.py
import qtawesome as qta
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QWidget, QLineEdit, QComboBox, QSlider, 
                               QScrollArea, QStackedWidget, QSpinBox)
from PySide6.QtCore import Qt, QSize, Signal


from core.signal_hub import global_signals
from core.project_manager import project_manager

class PropertiesPanel(QFrame):
    # Emits item_id, property_name, new_value
    property_changed = Signal(str, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.current_item_id = ""
        self.current_item_props = {}
        self.current_sub_type = ""
        
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
            QSpinBox {
                background-color: rgba(26, 26, 26, 0.8); border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px; color: #d1d1d1; padding: 4px; font-family: monospace;
            }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; } /* Clean look */
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

    def on_clip_selected(self, clip_id: str):
        """Triggered automatically when the Timeline shouts 'clip_selected'."""
        print(f"\nPROPERTIES HEARD SIGNAL: Timeline selected clip '{clip_id}'")
        
        # 1. Ask the Project Manager for the actual clip data
        if not project_manager.current_project:
            return
            
        selected_clip = None
        for track in project_manager.current_project.tracks:
            for clip in track.clips:
                if clip.clip_id == clip_id:
                    selected_clip = clip
                    break
                    
        # 2. If we found the clip, tell the UI to show its data
        if selected_clip:
            self.populate_ui(selected_clip)
        else:
            print("   -> Error: Could not find clip data in backend!")

    def on_clip_deselected(self):
        """Triggered when the user clicks the empty background of the timeline."""
        print("\nPROPERTIES PANEL: Selection cleared. Hiding settings.")
        self.clear_ui()

    def populate_ui(self, clip_data):
        """Reads the clip data and prepares to draw sliders/buttons."""
        print(f"   -> Waking up UI for: {clip_data.file_path}")
        print(f"   -> Media Type: {clip_data.clip_type}")
        print(f"   -> Duration: {clip_data.start_time}ms to {clip_data.end_time}ms")
        
        # NOTE: Your actual UI logic to show/hide sliders based on clip_type 
        # (e.g., showing Word Editor for subtitles) will go here!

    def clear_ui(self):
        """Hides the properties when nothing is selected."""
        # NOTE: Your actual UI logic to clear or disable the panel goes here.
        pass

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
            
            # Map specific properties dynamically
            if item_type == 'caption':
                self.input_text_caption.blockSignals(True)
                self.input_text_caption.setText(item_props.get("text", ""))
                self.input_text_caption.blockSignals(False)
            elif item_type in ['transition_in', 'transition_out']:
                current_trans = item_props.get(item_type, "Cross Dissolve")
                self.combo_transition.blockSignals(True)
                idx = self.combo_transition.findText(current_trans)
                if idx >= 0: self.combo_transition.setCurrentIndex(idx)
                self.combo_transition.blockSignals(False)
            
            self.stack.setCurrentWidget(page)
        else:
            self.lbl_title.setText("Properties")
            self.lbl_icon.setPixmap(qta.icon('mdi6.cog-outline', color='#e66b2c').pixmap(14, 14))
            self.stack.setCurrentWidget(self.page_empty)

    def _on_prop_change(self, prop_name, new_val):
        if self.current_item_id:
            self.property_changed.emit(self.current_item_id, prop_name, new_val)

    def _apply_transition_to_all(self):
        if self.current_item_id and self.current_item_props:
            track = self.current_item_props.get("track")
            current_trans = self.combo_transition.currentText()
            # Pass a package mapping track ID and transition name to the timeline
            self.property_changed.emit(
                self.current_item_id, 
                "apply_transition_to_all", 
                {"track": track, "transition": current_trans}
            )

    # --- UI Component Builders ---

    def _add_section(self, layout, title):
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #d1d1d1; font-size: 11px; font-weight: bold; margin-top: 10px; margin-bottom: 2px;")
        layout.addWidget(lbl)

    def _add_slider_row(self, layout, label_text, min_val, max_val, default_val, suffix=""):
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
        
        controls_layout.addWidget(slider)
        controls_layout.addWidget(val_lbl)
        row.addWidget(controls)
        layout.addLayout(row)
        return slider

    def _add_xy_row(self, layout, label_text, default_x=0, default_y=0):
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

        controls_layout.addWidget(x_spin)
        controls_layout.addWidget(y_spin)
        row.addWidget(controls)
        layout.addLayout(row)
        return x_spin, y_spin

    def _add_combo_row(self, layout, label_text, items, default_index=0):
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
        
        row.addWidget(combo)
        layout.addLayout(row)
        return combo

    def _add_color_row(self, layout, label_text, hex_color):
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
        # Connect to signal
        self.input_text_caption.textChanged.connect(lambda t: self._on_prop_change("text", t))
        layout.addWidget(self.input_text_caption)

        self._add_section(layout, "Typography")
        self._add_combo_row(layout, "Font Family", ["Roboto", "Arial", "Sour Gummy", "Montserrat"])
        self._add_slider_row(layout, "Font Size", 10, 200, 40)
        self._add_color_row(layout, "Text Color", "#FFFFFF")
        self._add_color_row(layout, "Background", "transparent")
        
        self._add_section(layout, "Transform")
        self._add_xy_row(layout, "Position", 0, 0)
        self._add_slider_row(layout, "Scale", 10, 300, 100, "%")
        self._add_slider_row(layout, "Rotation", -180, 180, 0, "°")
        self._add_slider_row(layout, "Opacity", 0, 100, 100, "%")

        return scroll

    def _create_video_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Transform")
        self._add_xy_row(layout, "Position", 0, 0)
        self._add_slider_row(layout, "Scale", 10, 400, 100, "%")
        self._add_slider_row(layout, "Rotation", -180, 180, 0, "°")
        self._add_slider_row(layout, "Opacity", 0, 100, 100, "%")

        self._add_section(layout, "Time & Playback")
        self._add_slider_row(layout, "Speed", 10, 500, 100, "%")
        
        self._add_section(layout, "Audio")
        self._add_slider_row(layout, "Volume", -60, 12, 0, "dB")

        return scroll

    def _create_image_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Transform")
        self._add_xy_row(layout, "Position", 0, 0)
        self._add_slider_row(layout, "Scale", 10, 400, 100, "%")
        self._add_slider_row(layout, "Rotation", -180, 180, 0, "°")
        self._add_slider_row(layout, "Opacity", 0, 100, 100, "%")

        self._add_section(layout, "Style")
        self._add_combo_row(layout, "Blend Mode", ["Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten"])
        self._add_slider_row(layout, "Corner Radius", 0, 200, 0, "px")

        return scroll

    def _create_audio_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Mixer")
        self._add_slider_row(layout, "Volume", -60, 12, 0, "dB")
        self._add_slider_row(layout, "Pan", -100, 100, 0)

        self._add_section(layout, "Fades")
        self._add_slider_row(layout, "Fade In", 0, 100, 0, "s")
        self._add_slider_row(layout, "Fade Out", 0, 100, 0, "s")
        
        self._add_section(layout, "Time")
        self._add_slider_row(layout, "Speed", 10, 400, 100, "%")
        self._add_slider_row(layout, "Pitch", -12, 12, 0, "st")

        return scroll

    def _create_effect_page(self):
        scroll, layout = self._create_scrollable_container()

        self._add_section(layout, "Effect Settings")
        self._add_combo_row(layout, "Effect Type", ["Gaussian Blur", "Cinematic Glow", "Color Grade", "Vignette"])
        
        self._add_section(layout, "Parameters")
        self._add_slider_row(layout, "Intensity", 0, 100, 100, "%")
        self._add_slider_row(layout, "Radius/Spread", 0, 200, 50, "px")
        self._add_color_row(layout, "Color Tint", "#e66b2c")
        
        self._add_section(layout, "Compositing")
        self._add_combo_row(layout, "Blend Mode", ["Normal", "Add", "Screen", "Multiply"])
        self._add_slider_row(layout, "Opacity", 0, 100, 100, "%")

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
        slider_dur = self._add_slider_row(layout, "Duration", 1, 50, 10, " frames")
        slider_dur.valueChanged.connect(
            lambda v: self._on_prop_change(f"{self.current_sub_type}_duration", v)
        )
        
        slider_align = self._add_slider_row(layout, "Alignment Center", -100, 100, 0, "%")
        slider_align.valueChanged.connect(
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
        self.combo_clip_effect = self._add_combo_row(layout, "Select Effect", ["Cinematic Glow", "Gaussian Blur", "VHS Overlay", "Edge Detect"])
        self.combo_clip_effect.currentTextChanged.connect(
            lambda t: self._on_prop_change("primary_effect", t)
        )
        
        self._add_section(layout, "Effect Speed / Timing")
        slider_speed = self._add_slider_row(layout, "Playback Speed", 10, 500, 100, "%")
        slider_speed.valueChanged.connect(lambda v: self._on_prop_change("effect_speed", v))
        
        self._add_section(layout, "Effect Intensity")
        slider_amount = self._add_slider_row(layout, "Amount", 0, 100, 100, "%")
        slider_amount.valueChanged.connect(lambda v: self._on_prop_change("effect_amount", v))
        
        self._add_section(layout, "Masking")
        slider_feather = self._add_slider_row(layout, "Feather", 0, 100, 0, "px")
        slider_feather.valueChanged.connect(lambda v: self._on_prop_change("effect_feather", v))
        
        return scroll