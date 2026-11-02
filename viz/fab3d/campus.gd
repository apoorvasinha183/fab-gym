extends Node3D
## The campus, streamed around the viewer (docs/FAB-3D.md). Only cells near the viewer are built: full detail within
## NEAR metres (each tool an instance of its kind's saved scene, the rail and its carriers), coloured boxes to FAR (one
## multimesh a cell), nothing beyond. Tools are built a few a frame so walking never stalls. Their states and the
## carriers come from the helper's live run, asked only for the cells held here. From the SMT2020 testbed; a gigafab-style
## layout of our own design; not a real fab.

signal ready_to_go

const NEAR := 48.0
const FAR := 120.0
const BUDGET := 24            # tool instances built a frame
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
var _since := 0.0
var full_ids: Array = []


static func w(x: float, y: float, z: float) -> Vector3:
	# plan (east, north, up) to Godot (x, up, -north)
	return Vector3(x, z, -y)


func _ready() -> void:
	var f := FileAccess.open("res://data/campus.json", FileAccess.READ)
	data = JSON.parse_string(f.get_as_text())
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
	rail_mat.albedo_color = Color(0.55, 0.57, 0.6)
	rail_mat.metallic = 0.8
	rail_mat.roughness = 0.35
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
	ready_to_go.emit()


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
	var v := viewer_plan()
	var want := {}
	var r := int(ceil(FAR / size)) + 1
	var ix0 := int(floor(v.x / size))
	var iy0 := int(floor(v.y / size))
	for ix in range(ix0 - r, ix0 + r + 1):
		for iy in range(iy0 - r, iy0 + r + 1):
			var cid := "%d,%d" % [ix, iy]
			if not data["cells"].has(cid):
				continue
			var d := cell_centre(cid).distance_to(v)
			if d <= NEAR:
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
	return Transform3D(Basis(Vector3.UP, yaw), w(cx, cy, float(heights["clean_z"])))


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
	node.add_child(mmi)


func _build_rail(node: Node3D, cell: Dictionary) -> void:
	var st: Array = cell["stretches"]
	if st.is_empty():
		return
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = box_mesh
	mm.instance_count = st.size()
	for k in st.size():
		var ab: PackedStringArray = str(st[k]).replace("n", "").split(">")
		var a: Vector3 = node_pos[int(ab[0])]
		var b: Vector3 = node_pos[int(ab[1])]
		var mid := (a + b) / 2.0
		var d := b - a
		var L := maxf(d.length(), 0.01)
		var rb := Basis(Vector3.UP, atan2(d.x, d.z)).scaled(Vector3(0.14, 0.1, L))
		mm.set_instance_transform(k, Transform3D(rb, mid))
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = rail_mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(mmi)


# ------------------------------------------------------------------ the live run's answers

func apply_state(d: Dictionary) -> void:
	for k in d.get("tools", {}).keys():
		moods[int(k)] = d["tools"][k]
		_paint(int(k))
	for g in d.get("queues", {}).keys():
		queues[g] = d["queues"][g]
	stays = d.get("carriers", [])
	var live := {}
	for s in stays:
		live[int(s["vehicle"])] = true
	for v in carriers.keys():
		if not live.has(v):
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
	var at := {}
	for s in stays:
		var t_in := float(s["t_in"])
		var t_out := float(s["t_out"]) if s["t_out"] != null else 1e12
		if clock >= t_in and clock < t_out:
			at[int(s["vehicle"])] = s
	for v in at.keys():
		var s: Dictionary = at[v]
		var copper := bool(s["copper"])
		if carriers.has(v) and carriers[v]["copper"] != copper:
			carriers[v]["node"].queue_free()
			carriers.erase(v)
		if not carriers.has(v):
			var n: Node3D = carrier_scenes["copper" if copper else "standard"].instantiate()
			add_child(n)
			carriers[v] = {"node": n, "copper": copper}
		var ab: PackedStringArray = str(s["stretch"]).replace("n", "").split(">")
		var a: Vector3 = node_pos[int(ab[0])]
		var b: Vector3 = node_pos[int(ab[1])]
		var t_out2 := float(s["t_out"]) if s["t_out"] != null else float(s["t_in"]) + 1.0
		var u := clampf((clock - float(s["t_in"])) / maxf(t_out2 - float(s["t_in"]), 1e-6), 0.0, 1.0)
		var p := a.lerp(b, u) - Vector3(0, 0.9, 0)
		var node: Node3D = carriers[v]["node"]
		node.global_position = p
		var d := b - a
		if d.length() > 0.01:
			node.rotation.y = atan2(d.x, d.z)
		node.visible = true
	for v in carriers.keys():
		if not at.has(v):
			carriers[v]["node"].visible = false


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
