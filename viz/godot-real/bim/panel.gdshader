shader_type spatial;
// Columns, slabs, the raised floor and the filter ceiling (docs/BIM-3D.md).
#include "res://bim/panel.gdshaderinc"

void fragment() {
	vec3 a = panel_albedo();
	ALBEDO = a;
	ROUGHNESS = rough;
	METALLIC = metal;
	EMISSION = a * emit;
}
