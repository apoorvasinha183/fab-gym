extends Node3D
## The campus outside (docs/FAB-3D.md, F10): the permit set's rooftop air units, chillers and transformers, our roads,
## trees and exhaust stacks, modelled in Blender from the campus data; this script only hangs the signs, in the pixel
## font of the screen. From the SMT2020 testbed; not a real fab.

const FONT := preload("res://ui/fonts/kenpixel.ttf")
const LOGO := preload("res://exterior/art/fabgym-logo.png")        # cut from docs/img/fabgym-hero.jpg
const Looks := preload("res://looks.gd")


func setup(ext: Dictionary) -> void:
	Looks.dress(self, {"asphalt": Looks.pbr("asphalt_02", 4.0, Color(1, 1, 1), -1.0, "diff", true), "pad": Looks.pbr("concrete_pavement", 2.5, Color(1, 1, 1), -1.0, "diff", true),
			"curb": Looks.pbr("brushed_concrete", 1.5),
			"unit": Looks.pbr("metal_plate", 1.5, Color(0.9, 0.92, 0.93), 0.4),
			"chiller": Looks.pbr("metal_plate", 1.5, Color(0.8, 0.88, 0.85), 0.4),
			"transformer": Looks.pbr("metal_plate", 1.5, Color(0.55, 0.68, 0.6), 0.3),
			"louvre": Looks.pbr("corrugated_iron_02", 0.8, Color(0.6, 0.63, 0.66)),
			"coil": Looks.pbr("corrugated_iron_02", 0.8, Color(0.7, 0.74, 0.72)),
			"stack": Looks.pbr("metal_plate", 1.2, Color(0.85, 0.87, 0.9), 0.7),
			"bridge": _plain(Color(0.9, 0.91, 0.92), 0.55),
			"deck": Looks.pbr("smooth_concrete_floor", 3.0)})
	for s in ext["assumed"]["signs"]:
		var a: Array = s["at"]
		var at := Vector3(float(a[0]), float(a[2]), -float(a[1]))
		var yaw := -PI / 2 if str(s["facing"]) == "west" else 0.0
		match str(s.get("kind", "text")):
			"logo":
				_picture(LOGO, at, yaw, float(s["width"]), true)
			_:
				var l := Label3D.new()
				l.text = str(s["text"])
				if s.get("pixel", false):
					l.font = FONT
					l.font_size = 128
					l.pixel_size = float(s["size"]) / 128.0
					l.outline_size = 24
					l.outline_modulate = Color(0.07, 0.1, 0.33)
					l.modulate = Color(1, 1, 1)
				else:
					# the picture's sign: bold blue letters on a white board
					l.font_size = 96
					l.pixel_size = float(s["size"]) / 96.0
					l.outline_size = 0
					l.modulate = Color(0.14, 0.33, 0.55)
					var board := MeshInstance3D.new()
					var bm := BoxMesh.new()
					bm.size = Vector3(float(s["size"]) * 0.62 * l.text.length() + 0.8, float(s["size"]) * 1.8, 0.06)
					board.mesh = bm
					board.material_override = _plain(Color(0.97, 0.97, 0.98), 0.6)
					board.position = Vector3(0, 0, -0.05)
					l.add_child(board)
				l.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
				l.position = at
				l.rotation.y = yaw
				add_child(l)


func _plain(c: Color, rough: float) -> StandardMaterial3D:
	# a smooth finish with no fine pattern (ribbed sheet shimmered at a distance)
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	return m


func _picture(tex: Texture2D, at: Vector3, yaw: float, width: float, panel: bool) -> void:
	# a picture on the wall: the FabGYM logo on a white panel
	var h := width * float(tex.get_height()) / float(tex.get_width())
	var q := MeshInstance3D.new()
	var qm := QuadMesh.new()
	qm.size = Vector2(width, h)
	q.mesh = qm
	var m := StandardMaterial3D.new()
	m.albedo_texture = tex
	m.roughness = 0.7
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	q.material_override = m
	q.position = at
	q.rotation.y = yaw
	add_child(q)
	var back := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(width + (1.2 if panel else 0.8), h + (1.2 if panel else 0.8), 0.08)
	back.mesh = bm
	back.material_override = _plain(Color(0.98, 0.98, 0.99) if panel else Color(0.12, 0.14, 0.18), 0.6)
	back.position = Vector3(0, 0, -0.06)
	q.add_child(back)

