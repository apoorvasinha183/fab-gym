extends Node3D
## A worker in a cleanroom suit (docs/FAB-3D.md): plays one CC0 clip (kneeling at a tool that is down, walking a bay, at
## a load port) and wears its job's colour on the hood trim (our own convention: blue operators, orange maintenance,
## green engineers). From the SMT2020 testbed; not a real fab.

const TRIMS := {"operator": Color(0.23, 0.48, 0.84), "maintenance": Color(0.94, 0.54, 0.17), "engineer": Color(0.18, 0.62, 0.36)}


func dress(job: String, clip: String) -> void:
	var mi := _mesh(self)
	if mi:
		for s in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(s)
			if m and m.resource_name == "staff_trim":
				var t := StandardMaterial3D.new()
				t.albedo_color = TRIMS.get(job, TRIMS["operator"])
				mi.set_surface_override_material(s, t)
	var ap := _anim(self)
	if ap:
		var short := clip.trim_suffix("_Loop")
		for a in ap.get_animation_list():
			if a == clip or a == short:
				ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
				ap.play(a)
				ap.seek(randf() * 2.0, true)
				break


func _mesh(n: Node) -> MeshInstance3D:
	if n is MeshInstance3D:
		return n
	for c in n.get_children():
		var m := _mesh(c)
		if m:
			return m
	return null


func _anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var a := _anim(c)
		if a:
			return a
	return null
