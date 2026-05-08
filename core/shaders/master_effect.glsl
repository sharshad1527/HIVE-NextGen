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

void main() {
    vec4 texColor = texture(screenTexture, TexCoord);
    FragColor = vec4(texColor.rgb, texColor.a * opacity);
}
