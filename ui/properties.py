# ui/properties.py
"""
Dynamic, data-driven Properties Panel.
Builds its UI from JSON control schemas — presets define what appears,
effects can inject/hide controls. The panel is the "controller";
presets & effects are "joysticks".
"""

import qtawesome as qta
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLabel, QWidget, QLineEdit, QComboBox, QSlider,
                               QScrollArea, QStackedWidget, QSpinBox, QDoubleSpinBox,
                               QColorDialog, QCheckBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from core.signal_hub import global_signals
from core.project_manager import project_manager
from core.control_schema import get_schema_for_clip
from ui.font_picker import FontPickerButton


class PropertiesPanel(QFrame):
    # Emits item_id, property_name, new_value, save_state(bool)
    property_changed = Signal(str, str, object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.current_item_id = ""
        self.current_item_props = {}
        self.current_sub_type = ""
        self._block_signals = False
        self._dynamic_widgets = {}  # key -> widget mapping for current schema

        self.setStyleSheet("""
            QFrame#Panel {
                background-color: rgba(14, 14, 16, 0.90);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
        """)

        # --- Shared Styles ---
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
                background-color: #1f1f23; border: 1px solid #333338;
                border-radius: 6px; color: #d1d1d1; padding: 4px 28px 4px 8px; font-family: 'Inter', sans-serif; font-size: 11px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border; subcontrol-position: top right;
                width: 16px; border-left: 1px solid #333338;
                border-bottom: 1px solid #333338; border-top-right-radius: 4px; background: #2b2b30;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 16px; border-left: 1px solid #333338;
                border-bottom-right-radius: 4px; background: #2b2b30;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background: #3a3a40;
            }
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
                image: url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAiIGhlaWdodD0iNiIgdmlld0JveD0iMCAwIDEwIDYiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTUgMEwxMCA2SDBMNSAwWiIgZmlsbD0iI2QxZDFkMSIvPjwvc3ZnPg==');
                width: 7px; height: 5px;
            }
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
                image: url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAiIGhlaWdodD0iNiIgdmlld0JveD0iMCAwIDEwIDYiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTUgNkwwIDBIMTBMNSA2WiIgZmlsbD0iI2QxZDFkMSIvPjwvc3ZnPg==');
                width: 7px; height: 5px;
            }
        """

        self.slider_style = """
            QSlider::groove:horizontal { border-radius: 2px; height: 4px; background-color: #262626; }
            QSlider::handle:horizontal { background-color: #d1d1d1; border: none; height: 10px; width: 10px; margin: -3px 0; border-radius: 5px; }
            QSlider::handle:horizontal:hover { background-color: #ffffff; }
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

        self.checkbox_style = """
            QCheckBox { color: #d1d1d1; font-size: 10px; spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2); background-color: rgba(26,26,26,0.8); }
            QCheckBox::indicator:checked { background-color: #e66b2c; border: 1px solid #e66b2c; }
        """

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
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

        # Dynamic content area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(self.scroll_style)
        layout.addWidget(self.scroll)

        # Empty page (default)
        self._show_empty_page()

        # Connect signals
        global_signals.clip_selected.connect(self.on_clip_selected)
        global_signals.clip_deselected.connect(self.on_clip_deselected)

        if hasattr(global_signals, 'clip_transform_changed'):
            global_signals.clip_transform_changed.connect(self._on_external_transform)

    # ================================================================
    # Signal Handlers
    # ================================================================

    def on_clip_selected(self, item_type: str, clip_id: str):
        """Triggered when Timeline signals clip_selected."""
        if not project_manager.current_project:
            return

        selected_clip = None
        track = None
        for t in project_manager.current_project.tracks:
            for clip in t.clips:
                if clip.clip_id == clip_id:
                    selected_clip = clip
                    track = t
                    break

        if selected_clip:
            self.current_track = track.track_id
            self.populate_ui(selected_clip, item_type)

    def on_clip_deselected(self):
        self.clear_ui()

    def populate_ui(self, clip_data, explicit_item_type=None):
        """Reads clip data and dynamically builds the properties UI from schema."""
        props = clip_data.applied_effects if isinstance(clip_data.applied_effects, dict) else {}
        item_type = explicit_item_type if explicit_item_type else clip_data.clip_type

        self.current_item_id = clip_data.clip_id
        self.current_item_props = props
        self.current_sub_type = item_type

        # Resolve the controls schema
        schema = get_schema_for_clip(item_type, props)

        # Update header
        type_info = {
            'caption':        ("Text Properties", 'mdi6.format-text'),
            'video':          ("Video Properties", 'mdi6.movie-open-outline'),
            'image':          ("Image Properties", 'mdi6.image-outline'),
            'audio':          ("Audio Properties", 'mdi6.volume-high'),
            'effect':         ("Effect Properties", 'mdi6.auto-fix'),
            'transition_in':  ("Transition In", 'mdi6.transition'),
            'transition_out': ("Transition Out", 'mdi6.transition'),
            'clip_effect':    ("Clip Effects", 'mdi6.auto-fix'),
        }

        if item_type in type_info:
            title, icon = type_info[item_type]
            self.lbl_title.setText(title)
            self.lbl_icon.setPixmap(qta.icon(icon, color='#e66b2c').pixmap(14, 14))
        else:
            self._show_empty_page()
            return

        # Build the dynamic UI
        self._build_dynamic_ui(schema, props)

    def clear_ui(self):
        self.current_item_id = ""
        self.current_item_props = {}
        self.current_sub_type = ""
        self.lbl_title.setText("Properties")
        self.lbl_icon.setPixmap(qta.icon('mdi6.cog-outline', color='#e66b2c').pixmap(14, 14))
        self._show_empty_page()

    def show_properties(self, item_type, item_id, item_props):
        """Legacy compatibility wrapper. Still called by timeline item_clicked signal."""
        self.current_item_id = item_id
        self.current_item_props = item_props
        self.current_sub_type = item_type

        if not item_type or not item_id:
            self.clear_ui()
            return

        # Build a minimal clip-like dict for schema resolution
        clip_data_dict = dict(item_props) if isinstance(item_props, dict) else {}
        schema = get_schema_for_clip(item_type, clip_data_dict)

        type_info = {
            'caption':        ("Text Properties", 'mdi6.format-text'),
            'video':          ("Video Properties", 'mdi6.movie-open-outline'),
            'image':          ("Image Properties", 'mdi6.image-outline'),
            'audio':          ("Audio Properties", 'mdi6.volume-high'),
            'effect':         ("Effect Properties", 'mdi6.auto-fix'),
            'transition_in':  ("Transition In", 'mdi6.transition'),
            'transition_out': ("Transition Out", 'mdi6.transition'),
            'clip_effect':    ("Clip Effects", 'mdi6.auto-fix'),
        }

        if item_type in type_info:
            title, icon = type_info[item_type]
            self.lbl_title.setText(title)
            self.lbl_icon.setPixmap(qta.icon(icon, color='#e66b2c').pixmap(14, 14))
            self._build_dynamic_ui(schema, clip_data_dict)
        else:
            self.clear_ui()

    # ================================================================
    # Dynamic UI Builder
    # ================================================================

    def _show_empty_page(self):
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        lbl = QLabel("Select an item on the timeline\nto view properties.")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #555555; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl)
        self.scroll.setWidget(widget)
        self._dynamic_widgets.clear()

    def _build_dynamic_ui(self, schema: list, current_values: dict):
        """Builds the entire properties UI from a controls_schema list."""
        self._block_signals = True
        self._dynamic_widgets.clear()

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(15, 5, 15, 20)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignTop)

        for section in schema:
            section_title = section.get("section", "")
            controls = section.get("controls", [])

            if not controls:
                continue

            # Section header
            if section_title:
                self._add_section_header(layout, section_title)

            # Build each control
            for control in controls:
                ctrl_type = control.get("type", "")
                key = control.get("key", "")
                label = control.get("label", key.replace("_", " ").title())

                if ctrl_type == "slider":
                    self._build_slider(layout, key, label, control, current_values)
                elif ctrl_type == "float_spin":
                    self._build_float_spin(layout, key, label, control, current_values)
                elif ctrl_type == "combo":
                    self._build_combo(layout, key, label, control, current_values)
                elif ctrl_type == "color":
                    self._build_color(layout, key, label, control, current_values)
                elif ctrl_type == "font":
                    self._build_font(layout, key, label, control, current_values)
                elif ctrl_type == "text":
                    self._build_text(layout, key, label, control, current_values)
                elif ctrl_type == "checkbox":
                    self._build_checkbox(layout, key, label, control, current_values)
                elif ctrl_type == "xy":
                    self._build_xy(layout, key, label, control, current_values)
                elif ctrl_type == "button":
                    self._build_button(layout, key, label, control)
                elif ctrl_type == "effect_dropdown":
                    self._build_effect_dropdown(layout, key, label, current_values)

        layout.addStretch()
        self.scroll.setWidget(content)
        self._block_signals = False

    # ================================================================
    # Control Builders
    # ================================================================

    def _add_section_header(self, layout, title):
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #d1d1d1; font-size: 11px; font-weight: bold; margin-top: 10px; margin-bottom: 2px;")
        layout.addWidget(lbl)

    def _build_slider(self, layout, key, label, control, values):
        min_val = control.get("min", 0)
        max_val = control.get("max", 100)
        default = control.get("default", min_val)
        suffix = control.get("suffix", "")
        current = values.get(key, default)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        controls = QWidget()
        controls.setFixedWidth(140)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(int(current))
        slider.setStyleSheet(self.slider_style)

        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setValue(int(current))
        if suffix:
            spin.setSuffix(suffix if suffix.startswith(" ") else f" {suffix}")
        spin.setFixedWidth(70)
        spin.setStyleSheet(self.spinbox_style)
        spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # Cross-couple slider and spinbox
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)

        # Value emits
        slider.sliderReleased.connect(lambda s=slider, k=key: self._on_prop_change(k, s.value(), commit=True))
        slider.valueChanged.connect(lambda v, k=key: self._on_prop_change(k, v, commit=False))
        # Ensure exact typing triggers a permanent change
        spin.editingFinished.connect(lambda s=spin, k=key: self._on_prop_change(k, s.value(), commit=True))

        controls_layout.addWidget(slider)
        controls_layout.addWidget(spin)
        row.addWidget(controls)
        layout.addLayout(row)

        self._dynamic_widgets[key] = slider

    def _build_float_spin(self, layout, key, label, control, values):
        min_val = control.get("min", 0.0)
        max_val = control.get("max", 10.0)
        default = control.get("default", min_val)
        step = control.get("step", 0.1)
        suffix = control.get("suffix", "")
        current = values.get(key, default)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(step)
        spin.setValue(float(current))
        spin.setSuffix(f" {suffix}" if suffix else "")
        spin.setDecimals(1)
        spin.setFixedWidth(70)
        spin.setStyleSheet(self.spinbox_style)
        spin.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        spin.valueChanged.connect(lambda v, k=key: self._on_prop_change(k, v, commit=True))

        row.addWidget(spin)
        layout.addLayout(row)

        self._dynamic_widgets[key] = spin

    def _build_combo(self, layout, key, label, control, values):
        options = control.get("options", [])
        default = control.get("default", options[0] if options else "")
        current = values.get(key, default)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        combo = QComboBox()
        combo.addItems(options)
        combo.setStyleSheet(self.combo_style)
        combo.setFixedWidth(140)

        idx = combo.findText(str(current))
        if idx >= 0:
            combo.setCurrentIndex(idx)

        combo.currentTextChanged.connect(lambda t, k=key: self._on_prop_change(k, t, commit=True))

        row.addWidget(combo)
        layout.addLayout(row)

        self._dynamic_widgets[key] = combo

    def _build_color(self, layout, key, label, control, values):
        default = control.get("default", "#FFFFFF")
        current = values.get(key, default)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        btn = QPushButton()
        btn.setFixedSize(140, 22)
        btn.setCursor(Qt.PointingHandCursor)
        btn._current_color = current

        def update_style(b, hex_val):
            if hex_val == "transparent":
                b.setStyleSheet("""
                    QPushButton { background-color: rgba(26,26,26,0.8); border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; color: #808080; font-size: 9px; }
                    QPushButton:hover { border: 1px solid #ffffff; }
                """)
                b.setText("transparent")
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background-color: {hex_val}; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }}
                    QPushButton:hover {{ border: 1px solid #ffffff; }}
                """)
                b.setText("")

        update_style(btn, current)

        def pick_color(b=btn, k=key):
            initial = QColor(b._current_color) if b._current_color != "transparent" else QColor("#FFFFFF")
            color = QColorDialog.getColor(initial, self, "Pick Color")
            if color.isValid():
                hex_val = color.name()
                b._current_color = hex_val
                update_style(b, hex_val)
                self._on_prop_change(k, hex_val)

        btn.clicked.connect(pick_color)

        row.addWidget(btn)
        layout.addLayout(row)

        self._dynamic_widgets[key] = btn

    def _build_font(self, layout, key, label, control, values):
        default = control.get("default", "Roboto")
        current = values.get(key, default)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        picker = FontPickerButton(current)
        picker.setFixedWidth(140)
        picker.font_changed.connect(lambda f, k=key: self._on_prop_change(k, f, commit=True))

        row.addWidget(picker)
        layout.addLayout(row)

        self._dynamic_widgets[key] = picker

    def _build_text(self, layout, key, label, control, values):
        default = control.get("default", "")
        placeholder = control.get("placeholder", "")
        current = values.get(key, default)

        text_input = QLineEdit(str(current))
        text_input.setPlaceholderText(placeholder)
        text_input.setStyleSheet(self.input_style)
        text_input.textChanged.connect(lambda t, k=key: self._on_prop_change(k, t, commit=False))
        text_input.editingFinished.connect(lambda ti=text_input, k=key: self._on_prop_change(k, ti.text(), commit=True))

        layout.addWidget(text_input)

        self._dynamic_widgets[key] = text_input

    def _build_checkbox(self, layout, key, label, control, values):
        default = control.get("default", False)
        current = values.get(key, default)

        chk = QCheckBox(label)
        chk.setChecked(bool(current))
        chk.setStyleSheet(self.checkbox_style)
        chk.stateChanged.connect(lambda state, k=key: self._on_prop_change(k, state == Qt.Checked, commit=True))

        layout.addWidget(chk)

        self._dynamic_widgets[key] = chk

    def _build_xy(self, layout, key, label, control, values):
        min_val = control.get("min", -9999)
        max_val = control.get("max", 9999)
        default_x = control.get("default_x", 0)
        default_y = control.get("default_y", 0)

        # XY uses Position_X and Position_Y keys internally
        current_x = values.get("Position_X", default_x)
        current_y = values.get("Position_Y", default_y)

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        controls = QWidget()
        controls.setFixedWidth(140)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        # Remove Spinbox Arrows and Label explicitly to fix Squishing
        lbl_x = QLabel("X:")
        lbl_x.setStyleSheet("color: #808080; font-size: 10px; font-weight: bold;")
        x_spin = QSpinBox()
        x_spin.setRange(min_val, max_val)
        x_spin.setValue(int(current_x))
        x_spin.setButtonSymbols(QSpinBox.NoButtons)
        x_spin.setStyleSheet(self.spinbox_style + "QSpinBox { padding-right: 8px; }")
        x_spin.setAlignment(Qt.AlignCenter)

        lbl_y = QLabel("Y:")
        lbl_y.setStyleSheet("color: #808080; font-size: 10px; font-weight: bold;")
        y_spin = QSpinBox()
        y_spin.setRange(min_val, max_val)
        y_spin.setValue(int(current_y))
        y_spin.setButtonSymbols(QSpinBox.NoButtons)
        y_spin.setStyleSheet(self.spinbox_style + "QSpinBox { padding-right: 8px; }")
        y_spin.setAlignment(Qt.AlignCenter)

        x_spin.valueChanged.connect(lambda v: self._on_prop_change("Position_X", v, commit=True))
        y_spin.valueChanged.connect(lambda v: self._on_prop_change("Position_Y", v, commit=True))

        controls_layout.addWidget(lbl_x)
        controls_layout.addWidget(x_spin)
        controls_layout.addWidget(lbl_y)
        controls_layout.addWidget(y_spin)
        
        row.addWidget(controls)
        layout.addLayout(row)

        self._dynamic_widgets["Position_X"] = x_spin
        self._dynamic_widgets["Position_Y"] = y_spin

    def _build_button(self, layout, key, label, control):
        icon_name = control.get("icon", "mdi6.check-all")
        btn = QPushButton(qta.icon(icon_name, color='#e66b2c'), f" {label}")
        btn.setStyleSheet(self.btn_primary_style)
        btn.setCursor(Qt.PointingHandCursor)

        if key == "_apply_transition_to_all":
            btn.clicked.connect(self._apply_transition_to_all)

        layout.addWidget(btn)

    def _build_effect_dropdown(self, layout, key, label, values):
        """Builds a dropdown showing all applied effects on the clip,
        allowing the user to select which effect's controls to view."""
        applied = values.get("applied_effects", [])
        if isinstance(applied, str):
            applied = [applied]
        elif not isinstance(applied, list):
            applied = []

        primary = values.get("primary_effect", "")
        if primary and primary not in applied:
            applied.insert(0, primary)

        if not applied:
            applied = ["None"]

        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #808080; font-size: 10px;")
        row.addWidget(lbl)
        row.addStretch()

        combo = QComboBox()
        combo.addItems(applied)
        combo.setStyleSheet(self.combo_style)
        combo.setFixedWidth(140)

        if primary:
            idx = combo.findText(primary)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        combo.currentTextChanged.connect(lambda t: self._on_prop_change("primary_effect", t, commit=True))

        row.addWidget(combo)
        layout.addLayout(row)

        self._dynamic_widgets["_effect_selector"] = combo

    # ================================================================
    # Property Change Handler
    # ================================================================

    def _on_prop_change(self, prop_name, new_val, commit=True):
        if self.current_item_id and not self._block_signals:
            self.property_changed.emit(self.current_item_id, prop_name, new_val, commit)

    def _apply_transition_to_all(self):
        if self.current_item_id and self.current_item_props is not None:
            track = getattr(self, "current_track", None)
            if not track:
                return
            # Find the transition combo
            trans_key = self.current_sub_type  # "transition_in" or "transition_out"
            combo = self._dynamic_widgets.get(trans_key)
            current_trans = combo.currentText() if combo else "Cross Dissolve"
            self.property_changed.emit(
                self.current_item_id,
                "apply_transition_to_all",
                {"track": track, "transition": current_trans},
                True
            )

    # ================================================================
    # External Sync (Preview Player <-> Properties Panel)
    # ================================================================

    def _on_external_transform(self, clip_id, prop_name, value):
        """Called when the preview player drags a clip — update our widgets without emitting back."""
        if clip_id == self.current_item_id:
            self._block_signals = True

            widget = self._dynamic_widgets.get(prop_name)
            if widget:
                if isinstance(widget, QSpinBox):
                    widget.setValue(int(value))
                elif isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(value))
                elif isinstance(widget, QSlider):
                    widget.setValue(int(value))
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(str(value))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)

            self._block_signals = False