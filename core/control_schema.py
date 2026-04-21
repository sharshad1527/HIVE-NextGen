# core/control_schema.py
"""
Master registry of default control schemas per clip type.
When a clip has no preset or its preset lacks a controls_schema,
the Properties panel falls back to these defaults.

Presets override these by providing their own 'controls_schema' key.
Effects can inject/hide controls via 'effect_overrides'.
"""


def _convert_legacy_properties(properties: dict) -> list:
    """
    Converts a legacy preset 'properties' dict into the new controls_schema format.
    
    Legacy format:
        {"font_family": {"type": "combo", "options": [...], "default": "Roboto"}}
    
    New format:
        [{"section": "Settings", "controls": [{"key": "font_family", "type": "combo", ...}]}]
    """
    controls = []
    for key, definition in properties.items():
        if isinstance(definition, dict):
            control = {"key": key, "label": key.replace("_", " ").title()}
            control.update(definition)
            # Remap legacy "combo" with font options to "font" type
            if control.get("type") == "combo" and key.lower() in ("font_family", "font"):
                control["type"] = "font"
                control.pop("options", None)
            controls.append(control)
        else:
            controls.append({"key": key, "type": "text", "default": definition, "label": key.replace("_", " ").title()})
    
    return [{"section": "Settings", "controls": controls}] if controls else []


def get_schema_for_clip(item_type: str, clip_data: dict) -> list:
    """
    Resolves the full controls schema for a clip.
    
    Priority:
    1. Preset's controls_schema (if clip has a preset_name)
    2. Converted legacy preset properties
    3. Default schema for the clip_type
    
    Then applies effect_overrides if effects are applied.
    """
    import copy
    
    schema = None
    
    # 1. Try to load from preset
    preset_name = clip_data.get("preset_name")
    if preset_name:
        from core.preset_loader import get_preset_by_name
        category_map = {
            "caption": "captions", "effect": "effects", "transition": "transitions",
            "transition_in": "transitions", "transition_out": "transitions",
        }
        category = category_map.get(item_type, "")
        preset = get_preset_by_name(category, preset_name)
        if preset:
            if "controls_schema" in preset:
                schema = copy.deepcopy(preset["controls_schema"])
            elif "properties" in preset:
                schema = _convert_legacy_properties(preset["properties"])
    
    # 2. Fall back to defaults
    if not schema:
        schema = copy.deepcopy(DEFAULT_SCHEMAS.get(item_type, DEFAULT_SCHEMAS.get("empty", [])))

    # Ensure Transform section exists for visual items
    if item_type in ("caption", "video", "image"):
        has_transform = any(s.get("section") == "Transform" for s in schema)
        if not has_transform:
            transform_schema = next((s for s in DEFAULT_SCHEMAS.get(item_type, []) if s.get("section") == "Transform"), None)
            if transform_schema:
                schema.append(copy.deepcopy(transform_schema))

    # 3. Apply effect overrides (inject/hide controls)
    applied_effects = clip_data.get("applied_effects", [])
    if isinstance(applied_effects, str):
        applied_effects = [applied_effects]
    elif not isinstance(applied_effects, list):
        applied_effects = []
    
    primary_effect = clip_data.get("primary_effect", "")
    if primary_effect and primary_effect not in applied_effects:
        applied_effects.append(primary_effect)
    
    if applied_effects:
        from core.preset_loader import get_preset_by_name
        hide_keys = set()
        inject_sections = []
        
        for effect_name in applied_effects:
            effect_preset = get_preset_by_name("effects", effect_name)
            if effect_preset and "effect_overrides" in effect_preset:
                overrides = effect_preset["effect_overrides"]
                hide_keys.update(overrides.get("hide", []))
                inject_controls = overrides.get("inject", [])
                if inject_controls:
                    inject_sections.append({
                        "section": f"⚡ {effect_name}",
                        "controls": copy.deepcopy(inject_controls)
                    })
        
        # Remove hidden controls
        if hide_keys:
            for section in schema:
                section["controls"] = [
                    c for c in section.get("controls", []) 
                    if c.get("key") not in hide_keys
                ]
        
        # Append injected sections
        schema.extend(inject_sections)
    
    return schema


# =======================================================================
# DEFAULT SCHEMAS — Fallback when no preset is applied
# =======================================================================

DEFAULT_SCHEMAS = {
    "caption": [
        {
            "section": "Content",
            "controls": [
                {"key": "text", "type": "text", "default": "", "placeholder": "Caption text...", "label": "Text"},
            ]
        },
        {
            "section": "Typography",
            "controls": [
                {"key": "Font Family", "type": "font", "default": "Roboto", "label": "Font"},
                {"key": "Font Size", "type": "slider", "min": 8, "max": 300, "default": 48, "suffix": "px", "label": "Size"},
                {"key": "font_weight", "type": "combo", "options": ["Regular", "Bold", "Light", "Black"], "default": "Bold", "label": "Weight"},
                {"key": "Text Color", "type": "color", "default": "#FFFFFF", "label": "Text Color"},
                {"key": "Bg Color", "type": "color", "default": "transparent", "label": "Background"},
                {"key": "bg_opacity", "type": "slider", "min": 0, "max": 100, "default": 0, "suffix": "%", "label": "BG Opacity"},
            ]
        },
        {
            "section": "Text Layout",
            "controls": [
                {"key": "max_chars_per_line", "type": "slider", "min": 5, "max": 80, "default": 40, "suffix": " chars", "label": "Line Width"},
                {"key": "max_lines", "type": "slider", "min": 1, "max": 8, "default": 3, "label": "Max Lines"},
                {"key": "word_wrap", "type": "checkbox", "default": True, "label": "Word Wrap"},
                {"key": "text_align", "type": "combo", "options": ["Left", "Center", "Right"], "default": "Center", "label": "Alignment"},
            ]
        },
        {
            "section": "Outline & Shadow",
            "controls": [
                {"key": "outline_width", "type": "slider", "min": 0, "max": 15, "default": 2, "suffix": "px", "label": "Outline"},
                {"key": "outline_color", "type": "color", "default": "#000000", "label": "Outline Color"},
            ]
        },
        {
            "section": "Transform",
            "controls": [
                {"key": "Position_X", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position X"},
                {"key": "Position_Y", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position Y"},
                {"key": "Scale", "type": "slider", "min": 10, "max": 400, "default": 100, "suffix": "%", "label": "Scale"},
                {"key": "Rotation", "type": "slider", "min": -180, "max": 180, "default": 0, "suffix": "°", "label": "Rotation"},
                {"key": "Opacity", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Opacity"},
            ]
        },
    ],
    
    "video": [
        {
            "section": "Transform",
            "controls": [
                {"key": "Position_X", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position X"},
                {"key": "Position_Y", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position Y"},
                {"key": "Scale", "type": "slider", "min": 10, "max": 400, "default": 100, "suffix": "%", "label": "Scale"},
                {"key": "Rotation", "type": "slider", "min": -180, "max": 180, "default": 0, "suffix": "°", "label": "Rotation"},
                {"key": "Opacity", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Opacity"},
            ]
        },
        {
            "section": "Playback",
            "controls": [
                {"key": "Speed", "type": "slider", "min": 10, "max": 500, "default": 100, "suffix": "%", "label": "Speed"},
                {"key": "reverse", "type": "checkbox", "default": False, "label": "Reverse Playback"},
                {"key": "mirror", "type": "checkbox", "default": False, "label": "Mirror (Flip H)"},
            ]
        },
        {
            "section": "Audio",
            "controls": [
                {"key": "Volume", "type": "slider", "min": 0, "max": 200, "default": 100, "suffix": "%", "label": "Volume"},
                {"key": "Fade_In", "type": "float_spin", "min": 0.0, "max": 30.0, "default": 0.0, "step": 0.1, "suffix": "s", "label": "Fade In"},
                {"key": "Fade_Out", "type": "float_spin", "min": 0.0, "max": 30.0, "default": 0.0, "step": 0.1, "suffix": "s", "label": "Fade Out"},
            ]
        },
    ],
    
    "image": [
        {
            "section": "Transform",
            "controls": [
                {"key": "Position_X", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position X"},
                {"key": "Position_Y", "type": "slider", "min": -9999, "max": 9999, "default": 0, "label": "Position Y"},
                {"key": "Scale", "type": "slider", "min": 10, "max": 400, "default": 100, "suffix": "%", "label": "Scale"},
                {"key": "Rotation", "type": "slider", "min": -180, "max": 180, "default": 0, "suffix": "°", "label": "Rotation"},
                {"key": "Opacity", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Opacity"},
            ]
        },
        {
            "section": "Style",
            "controls": [
                {"key": "Blend_Mode", "type": "combo",
                 "options": ["Normal", "Multiply", "Screen", "Overlay", "Darken", "Lighten", "Add", "Difference", "Exclusion"],
                 "default": "Normal", "label": "Blend Mode"},
                {"key": "Corner_Radius", "type": "slider", "min": 0, "max": 200, "default": 0, "suffix": "px", "label": "Corner Radius"},
                {"key": "mirror", "type": "checkbox", "default": False, "label": "Mirror (Flip H)"},
            ]
        },
    ],
    
    "audio": [
        {
            "section": "Mixer",
            "controls": [
                {"key": "Volume", "type": "slider", "min": 0, "max": 200, "default": 100, "suffix": "%", "label": "Volume"},
                {"key": "Pan", "type": "slider", "min": -100, "max": 100, "default": 0, "suffix": "", "label": "Pan  ◀ L  R ▶"},
            ]
        },
        {
            "section": "Fades",
            "controls": [
                {"key": "Fade_In", "type": "float_spin", "min": 0.0, "max": 60.0, "default": 0.0, "step": 0.1, "suffix": "s", "label": "Fade In"},
                {"key": "Fade_Out", "type": "float_spin", "min": 0.0, "max": 60.0, "default": 0.0, "step": 0.1, "suffix": "s", "label": "Fade Out"},
            ]
        },
        {
            "section": "Time & Pitch",
            "controls": [
                {"key": "Speed", "type": "slider", "min": 10, "max": 400, "default": 100, "suffix": "%", "label": "Speed"},
                {"key": "Pitch", "type": "slider", "min": -12, "max": 12, "default": 0, "suffix": " st", "label": "Pitch (semitones)"},
            ]
        },
    ],
    
    "effect": [
        {
            "section": "Effect Settings",
            "controls": [
                {"key": "effect_type", "type": "combo", "options": ["Gaussian Blur", "Cinematic Glow", "Color Grade", "Vignette", "VHS Retro", "Digital Glitch"], "default": "Gaussian Blur", "label": "Effect Type"},
            ]
        },
        {
            "section": "Parameters",
            "controls": [
                {"key": "intensity", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Intensity"},
                {"key": "radius", "type": "slider", "min": 0, "max": 200, "default": 50, "suffix": "px", "label": "Radius"},
                {"key": "color_tint", "type": "color", "default": "#e66b2c", "label": "Color Tint"},
            ]
        },
        {
            "section": "Compositing",
            "controls": [
                {"key": "blend_mode", "type": "combo", "options": ["Normal", "Add", "Screen", "Multiply"], "default": "Normal", "label": "Blend Mode"},
                {"key": "Opacity", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Opacity"},
            ]
        },
    ],
    
    "transition_in": [
        {
            "section": "Transition Setting",
            "controls": [
                {"key": "transition_in", "type": "combo", "options": ["Cross Dissolve", "Dip to Black", "Wipe", "Zoom", "Slide", "Glitch"], "default": "Cross Dissolve", "label": "Type"},
                {"key": "transition_in_duration_sec", "type": "float_spin", "min": 0.1, "max": 8.0, "default": 0.5, "step": 0.1, "suffix": "s", "label": "Speed"},
                {"key": "transition_in_easing", "type": "combo", "options": ["Linear", "Ease In", "Ease Out", "Ease In-Out"], "default": "Linear", "label": "Easing"},
            ]
        },
        {
            "section": "Batch Actions",
            "controls": [
                {"key": "_apply_transition_to_all", "type": "button", "label": "Apply to All in Track", "icon": "mdi6.check-all"},
            ]
        },
    ],
    
    "transition_out": [
        {
            "section": "Transition Setting",
            "controls": [
                {"key": "transition_out", "type": "combo", "options": ["Cross Dissolve", "Dip to Black", "Wipe", "Zoom", "Slide", "Glitch"], "default": "Cross Dissolve", "label": "Type"},
                {"key": "transition_out_duration_sec", "type": "float_spin", "min": 0.1, "max": 8.0, "default": 0.5, "step": 0.1, "suffix": "s", "label": "Speed"},
                {"key": "transition_out_easing", "type": "combo", "options": ["Linear", "Ease In", "Ease Out", "Ease In-Out"], "default": "Linear", "label": "Easing"},
            ]
        },
        {
            "section": "Batch Actions",
            "controls": [
                {"key": "_apply_transition_to_all", "type": "button", "label": "Apply to All in Track", "icon": "mdi6.check-all"},
            ]
        },
    ],
    
    "clip_effect": [
        {
            "section": "Applied Effect",
            "controls": [
                {"key": "_effect_selector", "type": "effect_dropdown", "label": "Active Effect"},
            ]
        },
        {
            "section": "Effect Timing",
            "controls": [
                {"key": "effect_speed", "type": "slider", "min": 10, "max": 500, "default": 100, "suffix": "%", "label": "Speed"},
            ]
        },
        {
            "section": "Intensity",
            "controls": [
                {"key": "effect_amount", "type": "slider", "min": 0, "max": 100, "default": 100, "suffix": "%", "label": "Amount"},
            ]
        },
        {
            "section": "Masking",
            "controls": [
                {"key": "effect_feather", "type": "slider", "min": 0, "max": 100, "default": 0, "suffix": "px", "label": "Feather"},
            ]
        },
    ],
    
    "empty": [],
}
