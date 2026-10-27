shader_type spatial;
render_mode cull_disabled;
// The fab's outer walls (docs/BIM-3D.md). The cut-away hides everything above the global height bim_cut_z,
// so the building opens above the cleanroom; with the cut off it sits far above the roof.
#include "res://bim/panel.gdshaderinc"
global uniform float bim_cut_z;

void fragment() {
	if (wpos.y > bim_cut_z) {
		discard;
	}
	vec3 a = panel_albedo();
	ALBEDO = a;
	ROUGHNESS = rough;
	METALLIC = metal;
	EMISSION = a * emit;
}
