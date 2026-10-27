// Panelled surfaces mapped by world position: seams as lines every `cell` metres (Godot axes, y up).
// Shared by the structure's materials (docs/BIM-3D.md).
uniform vec3 base_color : source_color = vec3(0.8);
uniform vec3 line_color : source_color = vec3(0.6);
uniform vec3 cell = vec3(1.0);
uniform float line_frac = 0.03;
uniform float rough = 0.6;
uniform float metal = 0.0;
uniform float emit = 0.0;
varying vec3 wpos;
varying vec3 wnrm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float seams(vec2 p) {
	vec2 f = fract(p);
	vec2 w = fwidth(p);
	vec2 l = vec2(1.0) - smoothstep(vec2(line_frac), vec2(line_frac) + w, f);
	return max(l.x, l.y);
}

vec3 panel_albedo() {
	vec3 n = abs(wnrm);
	vec3 q = wpos / cell;
	float g;
	if (n.y >= n.x && n.y >= n.z) {
		g = seams(q.xz);
	} else if (n.x >= n.z) {
		g = seams(q.zy);
	} else {
		g = seams(q.xy);
	}
	return mix(base_color, line_color, g);
}
