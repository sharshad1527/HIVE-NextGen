// #shader vertex
#version 330 core

layout (location = 0) in vec3 aPos;
layout (location = 1) in vec2 aTexCoord;

out vec2 TexCoord;

uniform mat4 uProjection;

void main() {
    gl_Position = uProjection * vec4(aPos, 1.0);
    TexCoord = aTexCoord;
}

// #shader fragment
#version 330 core

out vec4 FragColor;
in vec2 TexCoord;

uniform sampler2D screenTexture;
uniform float opacity;
uniform vec2 uResolution;
uniform float uTime;

// --- UNIVERSAL EFFECT UNIFORMS ---
// These are controlled directly by JSON preset_properties.
// Prefix 'e_' is used for effect parameters.

// 1. Color Grade
uniform float e_color_brightness; // -1.0 to 1.0
uniform float e_color_contrast;   // -1.0 to 1.0
uniform float e_color_saturation; // -1.0 to 1.0
uniform float e_color_tint_r;     // 0.0 to 1.0
uniform float e_color_tint_g;
uniform float e_color_tint_b;

// 2. Blur / Glow
uniform float e_blur_radius;     // 0.0 to 50.0
uniform float e_glow_intensity;  // 0.0 to 2.0

// 3. Vignette
uniform float e_vignette_amount; // 0.0 to 1.0
uniform float e_vignette_radius; // 0.0 to 1.0

// 4. VHS / Glitch
uniform float e_vhs_noise;       // 0.0 to 1.0
uniform float e_vhs_chroma;      // 0.0 to 1.0 (Chromatic Aberration)
uniform float e_glitch_freq;     // 0.0 to 1.0
uniform float e_glitch_disp;     // 0.0 to 1.0

float rand(vec2 co) {
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void main() {
    vec2 uv = TexCoord;
    
    // --- 1. Glitch Distortion ---
    if (e_glitch_freq > 0.0) {
        float sliceY = floor(uv.y * (20.0 * (1.0 - e_glitch_freq)));
        float sliceH = rand(vec2(sliceY, uTime));
        if (sliceH < 0.1 * e_glitch_freq) {
            uv.x += (rand(vec2(uTime)) - 0.5) * 0.1 * e_glitch_disp;
        }
    }

    vec4 color;
    
    // --- 2. Blur / Chromatic Aberration ---
    if (e_blur_radius > 0.0 || e_vhs_chroma > 0.0) {
        float shift = e_vhs_chroma * 0.01;
        float blur = e_blur_radius * 0.005;
        
        vec4 sum = vec4(0.0);
        // Simple 5-tap box blur
        sum += texture(screenTexture, uv + vec2(-blur, -blur));
        sum += texture(screenTexture, uv + vec2(blur, -blur));
        sum += texture(screenTexture, uv + vec2(0.0, 0.0));
        sum += texture(screenTexture, uv + vec2(-blur, blur));
        sum += texture(screenTexture, uv + vec2(blur, blur));
        color = sum / 5.0;
        
        if (e_vhs_chroma > 0.0) {
            color.r = texture(screenTexture, vec2(uv.x + shift, uv.y)).r;
            color.b = texture(screenTexture, vec2(uv.x - shift, uv.y)).b;
        }
    } else {
        color = texture(screenTexture, uv);
    }

    // --- 3. VHS Noise & Scanlines ---
    if (e_vhs_noise > 0.0) {
        float n = (rand(uv + uTime) - 0.5) * e_vhs_noise * 0.2;
        color.rgb += n;
        float scanline = sin(uv.y * uResolution.y * 1.5) * 0.04 * e_vhs_noise;
        color.rgb -= scanline;
    }

    // --- 4. Color Grading ---
    // Brightness
    color.rgb += e_color_brightness;
    
    // Contrast
    color.rgb = (color.rgb - 0.5) * (e_color_contrast + 1.0) + 0.5;
    
    // Saturation
    float gray = dot(color.rgb, vec3(0.299, 0.587, 0.114));
    color.rgb = mix(vec3(gray), color.rgb, e_color_saturation + 1.0);
    
    // Tint
    color.rgb *= vec3(1.0 + e_color_tint_r, 1.0 + e_color_tint_g, 1.0 + e_color_tint_b);

    // --- 5. Glow ---
    if (e_glow_intensity > 0.0) {
        vec4 highlight = max(color - 0.5, 0.0) * e_glow_intensity;
        color.rgb += highlight.rgb;
    }

    // --- 6. Vignette ---
    if (e_vignette_amount > 0.0) {
        float dist = distance(uv, vec2(0.5, 0.5));
        float v = smoothstep(e_vignette_radius, e_vignette_radius - 0.5 * e_vignette_amount, dist);
        color.rgb *= v;
    }

    FragColor = vec4(color.rgb, color.a * opacity);
}
