extends Node3D
## The campus, streamed around the viewer (docs/FAB-3D.md). Only cells near the viewer are built: full detail within
## NEAR metres (each tool an instance of its kind's saved scene, the rail and its carriers), coloured boxes to FAR (one
## multimesh a cell), nothing beyond. Tools are built a few a frame so walking never stalls. Their states and the
## carriers come from the helper's live run, asked only for the cells held here. From the SMT2020 testbed; a gigafab-style
## layout of our own design; not a real fab.

signal ready_to_go

const NEAR := 48.0
const FAR := 120.0
const BUDGET := 12            # tool instances built a frame
const CHECK_EVERY := 0.25     # seconds between looks at which cells are wanted

var data: Dictionary
var size := 24.0
var heights: Dictionary
var kinds := {}               # kind -> PackedScene
var carrier_scenes := {}
var loaded := {}              # cell id -> {"level": int, "node": Node3D, "tools": Array}
var pending: Array = []       # [cell id, tool index] still to build
var tool_nodes := {}          # tool index -> Node3D
var moods := {}               # tool index -> mood
var queues := {}              # group -> lots waiting
var stays: Array = []         # carrier stays from the helper
var plan := {}                # vehicle -> its stays in order: [t_in, arrive, a, b, ride, at a port, copper]
var carriers := {}            # vehicle -> {"node": Node3D, "copper": bool}
var node_pos: Array = []      # track node -> Vector3 at rail height
var bays: Array = []
var viewer: Node3D
var clock := 0.0
var surfaces := {}            # kind -> {"lamp_green": [i], "lamp_amber": [i], "lamp_red": [i], "accent": [i]}
var lamp_on := {}
var lamp_off := {}
var area_mats := {}
var box_mesh := BoxMesh.new()
var box_mat := StandardMaterial3D.new()
var rail_mat := StandardMaterial3D.new()
var hanger_mat := StandardMaterial3D.new()
const VEHICLE_M_PER_MIN := 150.0   # the shop's vehicle speed (web/data/shop-real.txt, the simulator's 150 m a minute)
const CEIL := 13.0            # underside of the filter ceiling (the blueprint's cleanroom top), metres
var _since := 0.0
var paused := false           # set while the drone flies: no cells are loaded
var full_ids: Array = []


static func inside(n: Node) -> void:
	# everything inside the fabs on render layer 2, which the sun does not light (see main.gd)
	if n is VisualInstance3D and not (n is Light3D):
		n.layers = 2
	for c in n.get_children():
		inside(c)


static func w(x: float, y: float, z: float) -> Vector3:
	# plan (east, north, up) to Godot (x, up, -north)
	return Vector3(x, z, -y)


static func panel_mat(base: Color, line: Color, cell: Vector3, frac := 0.03, dots := 0, emit := 0.0, rough := 0.5) -> StandardMaterial3D:
	# a panelled surface mapped by world position: one panel a texture tile, its seams as lines, perforations as dots
	var n := 128
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	img.fill(base)
	var lw := maxi(1, int(n * frac))
	for i in n:
		for j in lw:
			img.set_pixel(i, j, line)
			img.set_pixel(j, i, line)
	if dots > 0:
		var step := n / dots
		for a in dots:
			for b in dots:
				for dx in 3:
					for dy in 3:
						img.set_pixel(clampi(a * step + step / 2 + dx - 1, 0, n - 1), clampi(b * step + step / 2 + dy - 1, 0, n - 1), base.lerp(line, 0.7))
	img.generate_mipmaps()
	var m := StandardMaterial3D.new()
	m.albedo_texture = ImageTexture.create_from_image(img)
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3(1.0 / cell.x, 1.0 / cell.y, 1.0 / cell.z)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	m.roughness = rough
	if emit > 0.0:
		m.emission_enabled = true
		m.emission_texture = m.albedo_texture
		m.emission = Color(1, 1, 1)
		m.emission_energy_multiplier = emit
	return m


func _ready() -> void:
	var f := FileAccess.open("res://data/campus.json", FileAccess.READ)
	data = JSON.parse_string(f.get_as_text())
	# Upgrade older prepared bundles whose phase column accidentally held wall orientation.
	if int(data.get("schema_version", 1)) < 2:
		var halls: Array = data["fabs"].filter(func(h): return h[5] == "fab")
		halls.sort_custom(func(a, b): return float(a[0]) < float(b[0]))
		for tool in data["tools"]:
			var x := (float(tool[4]) + float(tool[5])) / 2.0
			for phase in halls.size():
				if x >= float(halls[phase][0]) and x <= float(halls[phase][1]):
					tool[3] = phase
	size = float(data["cell_size"])
	heights = data["heights"]
	bays = data["bays"]
	for k in data["kinds"].keys():
		var p := "res://tools/%s.tscn" % k
		if ResourceLoader.exists(p):
			kinds[k] = load(p)
	carrier_scenes["standard"] = load("res://carriers/standard.tscn")
	carrier_scenes["copper"] = load("res://carriers/copper.tscn")
	for n in data["track"]["nodes"]:
		node_pos.append(w(float(n[0]), float(n[1]), float(heights["rail_z"])))
	box_mat.vertex_color_use_as_albedo = true
	box_mat.roughness = 0.7
	rail_mat.albedo_color = Color(0.86, 0.86, 0.84)
	rail_mat.metallic = 0.1
	rail_mat.roughness = 0.35
	hanger_mat.albedo_color = Color(0.62, 0.64, 0.67)
	hanger_mat.metallic = 0.2
	hanger_mat.roughness = 0.4
	for c in ["green", "amber", "red"]:
		var col: Color = {"green": Color(0.15, 1.0, 0.35), "amber": Color(1.0, 0.65, 0.1), "red": Color(1.0, 0.12, 0.1)}[c]
		var on := StandardMaterial3D.new()
		on.albedo_color = col
		on.emission_enabled = true
		on.emission = col
		on.emission_energy_multiplier = 4.0
		lamp_on[c] = on
		var off := StandardMaterial3D.new()
		off.albedo_color = col.darkened(0.75)
		lamp_off[c] = off
	for a in data["areas"].keys():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(str(data["areas"][a]["colour"]))
		m.roughness = 0.35
		area_mats[a] = m
	_learn_surfaces()
	_decorate()
	ready_to_go.emit()


func _decorate() -> void:
	# static detail, built once: a stripe of the area's colour at each bay's mouth, the area's name on a small sign
	# hung from the filter ceiling, yellow filter light over lithography (real fabs filter out the blue light that would
	# expose the resist), yellow safety lines down the spine
	var z := float(heights["clean_z"]) + 0.012
	var stripes := MultiMesh.new()
	stripes.transform_format = MultiMesh.TRANSFORM_3D
	stripes.use_colors = true
	stripes.mesh = box_mesh
	stripes.instance_count = bays.size()
	var deco := Node3D.new()
	deco.name = "decor"
	add_child(deco)
	var yellow := StandardMaterial3D.new()
	yellow.albedo_color = Color(1.0, 0.86, 0.45)
	yellow.emission_enabled = true
	yellow.emission = Color(1.0, 0.8, 0.35)
	yellow.emission_energy_multiplier = 1.4
	var rods := []
	for k in bays.size():
		var b: Array = bays[k]
		var area := str(b[4])
		var col := Color(str(data["areas"][area]["colour"])) if data["areas"].has(area) else Color(0.8, 0.8, 0.8)
		var x0 := float(b[0])
		var x1 := float(b[1])
		var y0 := minf(float(b[2]), float(b[3]))
		var y1 := maxf(float(b[2]), float(b[3]))
		var mouth := y0 if absf(y0) < absf(y1) else y1          # the bay's open end, on the spine
		var inward := 1.0 if mouth == y0 else -1.0
		stripes.set_instance_transform(k, Transform3D(Basis.from_scale(Vector3(x1 - x0 - 0.4, 0.02, 0.25)),
				w((x0 + x1) / 2.0, mouth + inward * 0.3, z + 0.005)))
		stripes.set_instance_color(k, col)
		var sign := Label3D.new()
		sign.text = area_name(area)
		sign.font_size = 40
		sign.pixel_size = 0.0075
		sign.outline_size = 0
		sign.modulate = Color(1, 1, 1)
		sign.render_priority = 2
		var sz := float(heights["clean_z"]) + 3.3
		sign.position = w((x0 + x1) / 2.0, mouth + inward * 0.25, sz)
		sign.rotation.y = 0.0 if inward > 0 else PI
		var plate := MeshInstance3D.new()
		var bm := BoxMesh.new()
		var pw := minf(x1 - x0 - 0.6, 0.17 * sign.text.length() + 0.7)
		bm.size = Vector3(pw, 0.46, 0.05)
		plate.mesh = bm
		var pm := StandardMaterial3D.new()
		pm.albedo_color = col.darkened(0.2)
		pm.emission_enabled = true
		pm.emission = col
		pm.emission_energy_multiplier = 0.25
		plate.material_override = pm
		plate.position = Vector3(0, 0, -0.04)
		sign.add_child(plate)
		deco.add_child(sign)
		for e in [-0.42, 0.42]:
			var at := sign.position + Basis(Vector3.UP, sign.rotation.y) * Vector3(pw * e, 0, -0.04)
			rods.append(Transform3D(Basis.from_scale(Vector3(0.02, CEIL - sz - 0.23, 0.02)), Vector3(at.x, (CEIL + sz + 0.23) / 2.0, at.z)))
		if area == "Litho":
			var q := MeshInstance3D.new()
			var qb := BoxMesh.new()
			qb.size = Vector3(x1 - x0 - 0.1, 0.02, y1 - y0 - 0.1)
			q.mesh = qb
			q.material_override = yellow
			q.position = w((x0 + x1) / 2.0, (y0 + y1) / 2.0, CEIL - 0.015)
			q.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			deco.add_child(q)
			var l := OmniLight3D.new()
			l.light_color = Color(1.0, 0.82, 0.4)
			l.light_energy = 1.4
			l.omni_range = maxf(x1 - x0, y1 - y0) * 0.75
			l.shadow_enabled = false
			l.position = w((x0 + x1) / 2.0, (y0 + y1) / 2.0, float(heights["clean_z"]) + 4.0)
			deco.add_child(l)
	var fm := MultiMeshInstance3D.new()
	fm.multimesh = stripes
	var fmat := StandardMaterial3D.new()
	fmat.vertex_color_use_as_albedo = true
	fmat.roughness = 0.5
	fm.material_override = fmat
	fm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	deco.add_child(fm)
	var rm := MultiMesh.new()
	rm.transform_format = MultiMesh.TRANSFORM_3D
	rm.mesh = box_mesh
	rm.instance_count = rods.size()
	for k in rods.size():
		rm.set_instance_transform(k, rods[k])
	var rmi := MultiMeshInstance3D.new()
	rmi.multimesh = rm
	rmi.material_override = hanger_mat
	deco.add_child(rmi)
	# yellow safety lines down each side of the spine, in each fab
	for f in data["fabs"]:
		if str(f[5]) != "fab":
			continue
		for side in [-3.6, 3.6]:
			var line := MeshInstance3D.new()
			var lb := BoxMesh.new()
			lb.size = Vector3(float(f[1]) - float(f[0]) - 2.0, 0.02, 0.12)
			line.mesh = lb
			var lm := StandardMaterial3D.new()
			lm.albedo_color = Color(1.0, 0.82, 0.1)
			line.material_override = lm
			line.position = w((float(f[0]) + float(f[1])) / 2.0, side, z + 0.01)
			deco.add_child(line)
	inside(deco)


func _learn_surfaces() -> void:
	# which surface of each kind's mesh is a lamp or the area band, by its material's name
	for k in kinds.keys():
		var inst: Node3D = kinds[k].instantiate()
		var mi := _mesh_of(inst)
		var found := {"lamp_green": [], "lamp_amber": [], "lamp_red": [], "accent": []}
		if mi:
			for i in mi.mesh.get_surface_count():
				var m := mi.mesh.surface_get_material(i)
				if m and found.has(m.resource_name):
					found[m.resource_name].append(i)
		surfaces[k] = found
		inst.free()


func _mesh_of(n: Node) -> MeshInstance3D:
	if n is MeshInstance3D:
		return n
	for c in n.get_children():
		var m := _mesh_of(c)
		if m:
			return m
	return null


func viewer_plan() -> Vector2:
	var p := viewer.global_position if viewer else Vector3.ZERO
	return Vector2(p.x, -p.z)


func cell_centre(cid: String) -> Vector2:
	var b: Array = data["cells"][cid]["bounds"]
	return Vector2((float(b[0]) + float(b[1])) / 2.0, (float(b[2]) + float(b[3])) / 2.0)


func _process(dt: float) -> void:
	_since += dt
	if _since >= CHECK_EVERY:
		_since = 0.0
		update_cells()
	var n := 0
	while n < BUDGET and not pending.is_empty():
		var job: Array = pending.pop_front()
		if loaded.has(job[0]) and loaded[job[0]]["level"] == 2:
			_build_tool(job[0], int(job[1]))
		n += 1
	_move_carriers()


func update_cells(sync := false) -> void:
	if paused:
		# the drone is up: the roofs are on, so nothing inside is drawn or built
		for cid in loaded.keys():
			_unload(cid)
		full_ids = []
		return
	var v := viewer_plan()
	var want := {}
	# outside on the ground the walls hide the tools: near cells stay as boxes until the visitor is up on the clean floor
	var outside := viewer != null and viewer.global_position.y < 3.0
	var r := int(ceil(FAR / size)) + 1
	var ix0 := int(floor(v.x / size))
	var iy0 := int(floor(v.y / size))
	for ix in range(ix0 - r, ix0 + r + 1):
		for iy in range(iy0 - r, iy0 + r + 1):
			var cid := "%d,%d" % [ix, iy]
			if not data["cells"].has(cid):
				continue
			var d := cell_centre(cid).distance_to(v)
			if d <= NEAR and not outside:
				want[cid] = 2
			elif d <= FAR:
				want[cid] = 1
	for cid in loaded.keys():
		if not want.has(cid) or want[cid] != loaded[cid]["level"]:
			_unload(cid)
	for cid in want.keys():
		if not loaded.has(cid):
			_load(cid, want[cid])
	if sync:
		while not pending.is_empty():
			var job: Array = pending.pop_front()
			if loaded.has(job[0]) and loaded[job[0]]["level"] == 2:
				_build_tool(job[0], int(job[1]))
	full_ids = []
	for cid in loaded.keys():
		if loaded[cid]["level"] == 2:
			full_ids.append(cid)


func _unload(cid: String) -> void:
	var c: Dictionary = loaded[cid]
	for i in c["tools"]:
		tool_nodes.erase(i)
	c["node"].queue_free()
	loaded.erase(cid)


func _load(cid: String, level: int) -> void:
	var node := Node3D.new()
	node.name = "cell_" + cid.replace(",", "_")
	add_child(node)
	loaded[cid] = {"level": level, "node": node, "tools": []}
	var cell: Dictionary = data["cells"][cid]
	if level == 1:
		_build_boxes(node, cell)
		return
	for i in cell["tools"]:
		pending.append([cid, int(i)])
	_build_rail(node, cell)
	for s in cell["stockers"]:
		var st: Array = data["stockers"][int(s)]
		var inst: Node3D = kinds["stocker"].instantiate()
		var long_x := float(st[1]) - float(st[0]) > float(st[3]) - float(st[2])
		inst.transform = Transform3D(Basis(Vector3.UP, PI / 2 if long_x else 0.0),
				w((float(st[0]) + float(st[1])) / 2.0, (float(st[2]) + float(st[3])) / 2.0, float(heights["clean_z"])))
		node.add_child(inst)
		inside(inst)


func tool_transform(t: Array) -> Transform3D:
	# t: [group, area, kind, phase, x0, x1, y0, y1, h]; a tool's front faces the middle of its bay
	var cx := (float(t[4]) + float(t[5])) / 2.0
	var cy := (float(t[6]) + float(t[7])) / 2.0
	var dx := float(t[5]) - float(t[4])
	var dy := float(t[7]) - float(t[6])
	var bay := _bay_of(cx, cy)
	var bx := cx
	var by := 0.0
	if not bay.is_empty():
		bx = (float(bay[0]) + float(bay[1])) / 2.0
		by = (float(bay[2]) + float(bay[3])) / 2.0
	var yaw := 0.0
	if dx > dy:
		yaw = PI / 2 if bx >= cx else -PI / 2
	else:
		yaw = PI if by >= cy else 0.0
	# 2% smaller across the floor: a tool's footprint ends exactly on the bay's partitions, and two faces in one plane
	# fight for the same pixels (the flickering patches seen from the corridors)
	return Transform3D(Basis(Vector3.UP, yaw) * Basis.from_scale(Vector3(0.98, 1.0, 0.98)), w(cx, cy, float(heights["clean_z"])))


func _bay_of(x: float, y: float) -> Array:
	for b in bays:
		if x >= float(b[0]) and x <= float(b[1]) and y >= min(float(b[2]), float(b[3])) and y <= max(float(b[2]), float(b[3])):
			return b
	return []


func _build_tool(cid: String, i: int) -> void:
	var t: Array = data["tools"][i]
	var kind := str(t[2])
	if not kinds.has(kind):
		return
	var inst: Node3D = kinds[kind].instantiate()
	inst.transform = tool_transform(t)
	inst.set_meta("tool", i)
	loaded[cid]["node"].add_child(inst)
	inside(inst)
	loaded[cid]["tools"].append(i)
	tool_nodes[i] = inst
	var mi := _mesh_of(inst)
	if mi and area_mats.has(str(t[1])):
		for s in surfaces[kind]["accent"]:
			mi.set_surface_override_material(s, area_mats[str(t[1])])
	_paint(i)


func _build_boxes(node: Node3D, cell: Dictionary) -> void:
	var tools: Array = cell["tools"]
	if tools.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = box_mesh
	mm.instance_count = tools.size()
	for k in tools.size():
		var t: Array = data["tools"][int(tools[k])]
		var dx := float(t[5]) - float(t[4])
		var dy := float(t[7]) - float(t[6])
		var h := float(t[8])
		var c := w((float(t[4]) + float(t[5])) / 2.0, (float(t[6]) + float(t[7])) / 2.0, float(heights["clean_z"]) + h / 2.0)
		mm.set_instance_transform(k, Transform3D(Basis().scaled(Vector3(dx, h, dy)), c))
		var area := str(t[1])
		var col := Color(str(data["areas"][area]["colour"])) if data["areas"].has(area) else Color(0.8, 0.8, 0.8)
		mm.set_instance_color(k, col.lerp(Color(0.9, 0.9, 0.88), 0.55))
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = box_mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.layers = 2
	node.add_child(mmi)


func _build_rail(node: Node3D, cell: Dictionary) -> void:
	# the overhead track: an aluminium channel (two side flanges under a cap, the vehicle's wheels run inside), hung
	# from the filter ceiling by a rod every 3 m. Sizes assumed.
	var st: Array = cell["stretches"]
	if st.is_empty():
		return
	var rz := float(heights["rail_z"])
	var parts: Array = []      # [Transform3D]
	var rods: Array = []
	for k in st.size():
		var ab: PackedStringArray = str(st[k]).replace("n", "").split(">")
		var a: Vector3 = node_pos[int(ab[0])]
		var b: Vector3 = node_pos[int(ab[1])]
		var d := b - a
		var L := d.length()
		if L < 0.02:
			continue
		var turn := Basis(Vector3.UP, atan2(d.x, d.z))
		var mid := (a + b) / 2.0
		# one solid bar: thin flanges were less than a pixel wide beyond about 20 m, and only sparkled
		parts.append(Transform3D(turn * Basis.from_scale(Vector3(0.22, 0.2, L + 0.02)), mid + Vector3(0, 0.02, 0)))
		var n := int(L / 3.0)
		for q in n + 1:
			var p := a.lerp(b, (q + 0.5) / float(n + 1))
			rods.append(Transform3D(Basis.from_scale(Vector3(0.05, CEIL - rz - 0.12, 0.05)), p + Vector3(0, (CEIL - rz + 0.12) / 2.0, 0)))
	# the cell's own centre: the multimeshes sit there, so a visibility range measures from the cell, not the origin
	var b4: Array = cell["bounds"]
	var centre := w((float(b4[0]) + float(b4[1])) / 2.0, (float(b4[2]) + float(b4[3])) / 2.0, rz)
	for pack in [[parts, rail_mat], [rods, hanger_mat]]:
		var list: Array = pack[0]
		if list.is_empty():
			continue
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = box_mesh
		mm.instance_count = list.size()
		for k in list.size():
			var tr: Transform3D = list[k]
			mm.set_instance_transform(k, Transform3D(tr.basis, tr.origin - centre))
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		mmi.position = centre
		mmi.material_override = pack[1]
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if pack[1] == hanger_mat:
			# the rods are thinner than a pixel far off, where they only sparkle: gone past 30 m from their cell
			mmi.visibility_range_end = 30.0
			mmi.visibility_range_end_margin = 6.0
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		mmi.layers = 2
		node.add_child(mmi)


# ------------------------------------------------------------------ the live run's answers

func apply_state(d: Dictionary) -> void:
	for k in d.get("tools", {}).keys():
		moods[int(k)] = d["tools"][k]
		_paint(int(k))
	for g in d.get("queues", {}).keys():
		queues[g] = d["queues"][g]
	stays = d.get("carriers", [])
	# each vehicle's stays, in order, worked out once per answer so a frame only looks up where the clock is
	plan = {}
	for s in stays:
		var v := int(s["vehicle"])
		var ab: PackedStringArray = str(s["stretch"]).replace("n", "").split(">")
		var a: Vector3 = node_pos[int(ab[0])]
		var b: Vector3 = node_pos[int(ab[1])]
		var t_in := float(s["t_in"])
		var ride: float = a.distance_to(b) / VEHICLE_M_PER_MIN
		var arrive: float = float(s["t_out"]) if s["t_out"] != null else t_in + ride
		var port: bool = str(data["track"]["nodes"][int(ab[1])][2]) in ["port", "stocker"]
		if not plan.has(v):
			plan[v] = []
		plan[v].append([t_in, arrive, a, b, ride, port, bool(s["copper"])])
	for v in plan.keys():
		plan[v].sort_custom(func(x: Array, y: Array) -> bool: return x[0] < y[0])
	for v in carriers.keys():
		if not plan.has(v):
			carriers[v]["node"].queue_free()
			carriers.erase(v)


func _paint(i: int) -> void:
	if not tool_nodes.has(i):
		return
	var mood := str(moods.get(i, "sleep"))
	var lit: String = {"work": "green", "tired": "green", "full": "green", "batch": "amber", "setup": "amber", "pm": "amber",
			"hold": "amber", "hurt": "red", "physio": "red"}.get(mood, "")
	var kind := str(data["tools"][i][2])
	var mi := _mesh_of(tool_nodes[i])
	if not mi:
		return
	for c in ["green", "amber", "red"]:
		for s in surfaces[kind]["lamp_" + c]:
			mi.set_surface_override_material(s, lamp_on[c] if c == lit else lamp_off[c])


func _move_carriers() -> void:
	# each vehicle on its latest stay begun by the clock. On a stretch it moves at the simulator's speed and reaches
	# the far end exactly when the simulator says it leaves it, so time spent queued behind another vehicle is spent
	# waiting at the near end. A stay the helper sends open-ended (still running when its 30-minute window closed) is
	# driven at speed and then stands. A vehicle standing over a tool's port or a stocker's lowers its pod on the
	# hoist belts and lifts it before its next stay (that gap in the simulator's stays is the transfer).
	var drop_full := float(heights["rail_z"]) - 0.9 - float(heights["port_z"])
	for v in plan.keys():
		var L: Array = plan[v]
		var k := -1
		for q in L.size():
			if float(L[q][0]) <= clock:
				k = q
			else:
				break
		if k < 0:
			if carriers.has(v):
				carriers[v]["node"].visible = false
			continue
		var s: Array = L[k]
		var next_in: float = float(L[k + 1][0]) if k + 1 < L.size() else 1e12
		var arrive: float = s[1]
		var a: Vector3 = s[2]
		var b: Vector3 = s[3]
		var ride: float = s[4]
		var copper: bool = s[6]
		if carriers.has(v) and carriers[v]["copper"] != copper:
			carriers[v]["node"].queue_free()
			carriers.erase(v)
		if not carriers.has(v):
			var n: Node3D = carrier_scenes["copper" if copper else "standard"].instantiate()
			add_child(n)
			inside(n)
			var belts := MeshInstance3D.new()
			var bb := BoxMesh.new()
			bb.size = Vector3(0.16, 1.0, 0.01)
			belts.mesh = bb
			belts.material_override = hanger_mat
			belts.visible = false
			n.add_child(belts)
			carriers[v] = {"node": n, "copper": copper, "hoist": n.find_child("hoist", true, false), "belts": belts}
		var p := b
		var drop := 0.0
		if clock < arrive:
			var leave := maxf(float(s[0]), arrive - ride)
			p = a.lerp(b, clampf((clock - leave) / maxf(ride, 1e-6), 0.0, 1.0))
		elif s[5] and next_in - arrive >= 0.5:
			# 12 simulated seconds down, held, 12 up before the next stay
			drop = clampf(minf(clock - arrive, next_in - clock) / 0.2, 0.0, 1.0) * drop_full
		var c: Dictionary = carriers[v]
		var node: Node3D = c["node"]
		node.position = p - Vector3(0, 0.9, 0)
		var d := b - a
		if d.length_squared() > 0.0001:
			node.rotation.y = atan2(-d.z, d.x)     # the vehicle's long side along the rail
		if c["hoist"]:
			c["hoist"].position.y = -drop
		var belts: MeshInstance3D = c["belts"]
		belts.visible = drop > 0.03
		if belts.visible:
			belts.scale = Vector3(1, drop, 1)
			belts.position = Vector3(0, 0.39 - drop / 2.0, 0)
		node.visible = true


# ------------------------------------------------------------------ what a visitor asks about

func tool_at(origin: Vector3, dir: Vector3) -> int:
	# the nearest built tool the ray from the camera passes through, by its footprint box; -1 when none
	var best := -1
	var best_t := 1e9
	for i in tool_nodes.keys():
		var t: Array = data["tools"][i]
		var lo := Vector3(min(float(t[4]), float(t[5])), float(heights["clean_z"]), -max(float(t[6]), float(t[7])))
		var hi := Vector3(max(float(t[4]), float(t[5])), float(heights["clean_z"]) + float(t[8]), -min(float(t[6]), float(t[7])))
		var hit = AABB(lo, hi - lo).intersects_ray(origin, dir)
		if hit != null:
			var dist := origin.distance_to(hit)
			if dist < best_t:
				best_t = dist
				best = i
	return best


func area_name(area: String) -> String:
	return str(data["areas"][area]["name"]) if data["areas"].has(area) else area


func stage_of(area: String) -> Dictionary:
	for s in data["stages"]:
		if area in s["areas"]:
			return s
	return {}
