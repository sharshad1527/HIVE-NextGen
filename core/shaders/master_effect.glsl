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

// Effect Uniforms
uniform int uEffectType; // 0: None, 1: Blur, 2: Glow, 3: Vignette, 4: ColorGrade, 5: VHS, 6: Glitch
uniform float uAmount;
uniform float uRadius;
uniform float uBrightness;
uniform float uContrast;
uniform float uSaturation;
uniform float uNoise;
uniform float uShift;
uniform vec2 uResolution;
uniform float uTime;

float rand(vec2 co) {
    return fract(sin(dot(co.xy ,vec2(12.9898,78.233))) * 43758.5453);
}

void main() {
    vec2 uv = TexCoord;
    vec4 color = texture(screenTexture, uv);
    
    // 1. VHS Effect (Scanlines and Chromatic Aberration)
    if (uEffectType == 5) {
        float shift = uShift * 0.01 * uAmount;
        float r = texture(screenTexture, vec2(uv.x + shift, uv.y)).r;
        float g = texture(screenTexture, uv).g;
        float b = texture(screenTexture, vec2(uv.x - shift, uv.y)).b;
        color = vec4(r, g, b, color.a);
        
        // Simple scanlines
        float scanline = sin(uv.y * uResolution.y * 1.5) * 0.04 * uAmount;
        color.rgb -= scanline;
        
        // Noise
        float n = (rand(uv + uTime) - 0.5) * uNoise * uAmount;
        color.rgb += n;
    }
    
    // 2. Glitch Effect
    if (uEffectType == 6) {
        float sliceY = floor(uv.y * 20.0);
        float sliceH = rand(vec2(sliceY, uTime));
        if (sliceH < 0.1 * uAmount) {
            uv.x += (rand(vec2(uTime)) - 0.5) * 0.1 * uAmount;
        }
        color = texture(screenTexture, uv);
    }
    
    // 3. Vignette
    if (uEffectType == 3) {
        float dist = distance(uv, vec2(0.5, 0.5));
        float vignette = smoothstep(uRadius, uRadius - 0.5 * uAmount, dist);
        color.rgb *= vignette;
    }
    
    // 4. Color Grade
    if (uEffectType == 4) {
        // Brightness
        color.rgb += uBrightness * uAmount;
        
        // Contrast
        color.rgb = (color.rgb - 0.5) * (uContrast * uAmount + 1.0) + 0.5;
        
        // Saturation
        float gray = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        color.rgb = mix(vec3(gray), color.rgb, uSaturation * uAmount + 1.0);
    }

    // 5. Basic Blur (Box blur approximation in one pass for performance)
    if (uEffectType == 1 || uEffectType == 2) {
        float blurRadius = uRadius * 0.005 * uAmount;
        vec4 blurColor = vec4(0.0);
        float total = 0.0;
        for (float x = -2.0; x <= 2.0; x++) {
            for (float y = -2.0; y <= 2.0; y++) {
                blurColor += texture(screenTexture, uv + vec2(x, y) * blurRadius);
                total += 1.0;
            }
        }
        blurColor /= total;
        
        if (uEffectType == 2) { // Glow
            color = color + blurColor * 0.5 * uAmount;
        } else {
            color = blurColor;
        }
    }

    FragColor = vec4(color.rgb, color.a * opacity);
}
