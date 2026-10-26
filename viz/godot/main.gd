extends Node3D
## A gigafab-style campus of our own design on the SMT2020 model (not a real fab), with a
## simulated run replayed: tools coloured by area and state, lots riding the overhead hoist,
## waiting lots stacked in towers at their bay's mouth.
##
## Data: res://data/scene.json, written by viz/prep.py.
## Keys: drag to orbit, right-drag or WASD to pan, wheel to zoom, 1-5 views, T tour,
## Space pause, +/- speed, H hide the panel.
## Film: godot --path viz/godot --write-movie out.avi --fixed-fps 30 -- --tour --quit

const SCENE := "res://data/scene.json"

var S: Dictionary
var t: float = 0.0            # fab minutes
var speed: float = 6.0        # fab minutes per real second
var paused := false
var tour := false
var tour_t := 0.0
var quit_after := false
var shot := ""
var shot_at := -1.0
var frames := 0

var tools_mm: MultiMesh
var beacons_mm: MultiMesh
var lots_mm: MultiMesh
var tool_state: PackedInt32Array
var tool_colour: Array = []
var state_i := 0
var cursor: PackedInt32Array
var lot_keys: Array = []
var lot_hot: Array = []

var cam: Camera3D
var pivot := Vector3(376, 0, 0)
var yaw := -0.55
var pitch := 0.62
var dist := 820.0
var hud: Label
var legend: Label
var caption: Label
var panel: Control

const STATE_NAMES := ["working", "idle", "maintenance", "broken down"]


func w(x: float, y: float, z: float) -> Vector3:
	# plan (east, north, up) to Godot (x, up, -north)
	return Vector3(x, z, -y)


func _ready() -> void:
	var f := FileAccess.open(SCENE, FileAccess.READ)
	if f == null:
		push_error("no %s: run python3 viz/prep.py --copy viz/godot/data/scene.json" % SCENE)
		return
	S = JSON.parse_string(f.get_as_text())
	var args := OS.get_cmdline_user_args()
	tour = args.has("--tour")
	quit_after = args.has("--quit")
	# --shot PATH SECONDS [VIEW]: save a picture after that many seconds of play and quit
	var si := args.find("--shot")
	if si >= 0:
		shot = args[si + 1]
		shot_at = float(args[si + 2])
		if args.size() > si + 3:
			var v: Array = VIEWS[int(args[si + 3])]
			pivot = v[0]
			yaw = v[1]
			pitch = v[2]
			dist = v[3]
	t = S["from"]
	_environment()
	_ground()
	_buildings()
	_bays()
	_tools()
	_rails()
	_labels()
	_lots()
	_camera()
	_hud()
	_apply_states_until(t)


func _environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("0b1220")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("8fa7c7")
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	env.glow_intensity = 0.6
	env.glow_bloom = 0.08
	env.ssao_enabled = true
	env.fog_enabled = true
	env.fog_light_color = Color("0b1220")
	env.fog_density = 0.0007
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -35, 0)
	sun.light_energy = 1.1
	sun.light_color = Color("fff1dc")
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 1400.0
	add_child(sun)


func mat(c: Color, emit := 0.0, alpha := 1.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(c.r, c.g, c.b, alpha)
	m.roughness = 0.75
	if alpha < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
	if emit > 0.0:
		m.emission_enabled = true
		m.emission = c
		m.emission_energy_multiplier = emit
	return m


func box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, m: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = Vector3(abs(x1 - x0), abs(z1 - z0), abs(y1 - y0))
	mi.mesh = b
	mi.material_override = m
	mi.position = w((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
	add_child(mi)
	return mi


func _ground() -> void:
	box(-1500, -1500, -0.6, 2500, 1500, -0.2, mat(Color("0f1622")))
	# the site
	box(-60, -280, -0.2, 920, 260, -0.05, mat(Color("161f2e")))


func _buildings() -> void:
	for b in S["buildings"]:
		var k: String = b["kind"]
		if k == "fab":
			# cleanroom floor, a low wall, and the building's volume as faint glass
			box(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], 0.0, mat(Color("1b2433")))
			var wall := mat(Color("3a4a63"))
			for side in [[b["x0"], b["y0"], b["x1"], b["y0"] + 0.6], [b["x0"], b["y1"] - 0.6, b["x1"], b["y1"]], [b["x0"], b["y0"], b["x0"] + 0.6, b["y1"]], [b["x1"] - 0.6, b["y0"], b["x1"], b["y1"]]]:
				box(side[0], side[1], 0.0, side[2], side[3], 4.0, wall)
			box(b["x0"], b["y0"], 0.0, b["x1"], b["y1"], b["h"], mat(Color("6c8db8"), 0.0, 0.05))
		elif k == "pad":
			box(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], b["h"], mat(Color("2a3344")))
		elif k == "gas":
			box(b["x0"], b["y0"], -0.05, b["x1"], b["y1"], 0.2, mat(Color("232d3d")))
			var n := 7
			for i in n:
				var cx: float = b["x0"] + (i + 0.5) * (b["x1"] - b["x0"]) / n
				var cy: float = (b["y0"] + b["y1"]) / 2.0
				var mi := MeshInstance3D.new()
				var c := CylinderMesh.new()
				c.top_radius = 5.0
				c.bottom_radius = 5.0
				c.height = b["h"]
				mi.mesh = c
				mi.material_override = mat(Color("c9d3e0"))
				mi.position = w(cx, cy, b["h"] / 2.0)
				add_child(mi)
		else:
			box(b["x0"], b["y0"], 0.0, b["x1"], b["y1"], b["h"], mat(Color("222c3c")))
	for br in S["bridges"]:
		box(br["x0"], br["y"] - 3.0, br["z"] - 2.5, br["x1"], br["y"] + 3.0, br["z"] + 2.5, mat(Color("7fb4ff"), 0.15, 0.35))


func _bays() -> void:
	for b in S["bays"]:
		var c := Color(S["areas"][b["area"]]["colour"])
		box(b["x0"] + 0.3, b["y0"], 0.0, b["x1"] - 0.3, b["y1"], 0.03, mat(c.darkened(0.72)))
		# the bay's aisle
		var cx: float = (b["x0"] + b["x1"]) / 2.0
		box(cx - 1.75, b["y0"], 0.03, cx + 1.75, b["y1"], 0.05, mat(Color("2b384d")))
	# the spines
	for i in range(S["buildings"].size()):
		var b: Dictionary = S["buildings"][i]
		if b["kind"] == "fab":
			box(b["x0"] + 4, -S["spine"] / 2.0, 0.0, b["x1"] - 4, S["spine"] / 2.0, 0.06, mat(Color("2f3d55")))


func _tools() -> void:
	var tl: Array = S["tools"]
	tools_mm = MultiMesh.new()
	tools_mm.transform_format = MultiMesh.TRANSFORM_3D
	tools_mm.use_colors = true
	var bm := BoxMesh.new()
	bm.size = Vector3.ONE
	tools_mm.mesh = bm
	tools_mm.instance_count = tl.size()
	tool_state.resize(tl.size())
	for i in tl.size():
		var tb: Dictionary = tl[i]
		var sx: float = (tb["x1"] - tb["x0"]) * 0.88
		var sy: float = (tb["y1"] - tb["y0"]) * 0.82
		var h: float = tb["h"]
		var basis := Basis().scaled(Vector3(sx, h, sy))
		tools_mm.set_instance_transform(i, Transform3D(basis, w((tb["x0"] + tb["x1"]) / 2.0, (tb["y0"] + tb["y1"]) / 2.0, h / 2.0)))
		var area: String = S["groups"][int(tb["g"])]["area"]
		tool_colour.append(Color(S["areas"][area]["colour"]))
		tool_state[i] = 1
		tools_mm.set_instance_color(i, _state_colour(i, 1))
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = tools_mm
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.roughness = 0.5
	m.emission_enabled = true
	m.emission = Color(0.12, 0.12, 0.12)
	mmi.material_override = m
	add_child(mmi)
	# a glowing beacon over a tool in maintenance (amber) or broken down (red)
	beacons_mm = MultiMesh.new()
	beacons_mm.transform_format = MultiMesh.TRANSFORM_3D
	beacons_mm.use_colors = true
	var sm := SphereMesh.new()
	sm.radius = 0.9
	sm.height = 1.8
	beacons_mm.mesh = sm
	beacons_mm.instance_count = tl.size()
	for i in tl.size():
		beacons_mm.set_instance_transform(i, Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO))
	var bi := MultiMeshInstance3D.new()
	bi.multimesh = beacons_mm
	var bmat := StandardMaterial3D.new()
	bmat.vertex_color_use_as_albedo = true
	bmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	bi.material_override = bmat
	bi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(bi)


func _state_colour(i: int, s: int) -> Color:
	var c: Color = tool_colour[i]
	match s:
		0:
			return c.lightened(0.15)
		1:
			return c.darkened(0.55)
		_:
			return Color("2a2f38")


func _rails() -> void:
	var rm := mat(Color("49d3ff"), 0.9)
	for r in S["rails"]:
		var a: Array = r[0]
		var b: Array = r[1]
		box(min(a[0], b[0]) - 0.15, min(a[1], b[1]) - 0.15, a[2] + 0.4, max(a[0], b[0]) + 0.15, max(a[1], b[1]) + 0.15, a[2] + 0.7, rm)


func _label(text: String, p: Vector3, size: int, c: Color) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.font_size = size
	l.pixel_size = 0.05
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.modulate = c
	l.outline_size = 12
	l.outline_modulate = Color(0, 0, 0, 0.85)
	l.position = p
	l.no_depth_test = true
	add_child(l)
	return l


func _labels() -> void:
	# area names at the back of their bays, alternating heights so neighbours do not collide
	var k := 0
	for lb in S["labels"]:
		var c := Color(S["areas"][lb["area"]]["colour"]).lightened(0.25)
		var back: float = lb["y"] + (22.0 if lb["y"] > 0 else -22.0)
		_label(lb["text"], w(lb["x"], back, 10.0 + 9.0 * (k % 3)), 80, c)
		k += 1
	for b in S["buildings"]:
		var bl := _label(b["label"], w((b["x0"] + b["x1"]) / 2.0, (b["y0"] + b["y1"]) / 2.0 if b["kind"] != "fab" else b["y1"] + 14.0, max(float(b["h"]), 10.0) + 14.0), 130, Color("e8eef7"))
		if b["kind"] != "fab":
			# support buildings are named only from afar
			bl.visibility_range_begin = 320.0
	for br in S["bridges"]:
		_label("OHT bridge", w((br["x0"] + br["x1"]) / 2.0, 0.0, br["z"] + 10.0), 120, Color("9fd0ff"))


func _lots() -> void:
	var L: Array = S["lots"]
	lots_mm = MultiMesh.new()
	lots_mm.transform_format = MultiMesh.TRANSFORM_3D
	lots_mm.use_colors = true
	var bm := BoxMesh.new()
	var f: float = S["foup"]
	bm.size = Vector3(f, f * 0.9, f)
	lots_mm.mesh = bm
	lots_mm.instance_count = L.size()
	cursor.resize(L.size())
	for i in L.size():
		lot_keys.append(L[i]["k"])
		lot_hot.append(L[i]["hot"])
		lots_mm.set_instance_color(i, Color("ff5a36") if L[i]["hot"] else Color("e8eef7"))
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = lots_mm
	var m := StandardMaterial3D.new()
	m.vertex_color_use_as_albedo = true
	m.emission_enabled = true
	m.emission = Color(0.35, 0.35, 0.35)
	m.roughness = 0.4
	mmi.material_override = m
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mmi)


func _camera() -> void:
	cam = Camera3D.new()
	cam.fov = 50
	cam.far = 6000
	add_child(cam)
	_place_camera()


func _place_camera() -> void:
	var dir := Vector3(cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw))
	cam.position = pivot + dir * dist
	cam.look_at(pivot, Vector3.UP)


func _text(t: String, size: int, c: Color) -> Label:
	var l := Label.new()
	l.text = t
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", c)
	return l


func _hud() -> void:
	var cl := CanvasLayer.new()
	add_child(cl)
	panel = Control.new()
	panel.set_anchors_preset(Control.PRESET_FULL_RECT)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cl.add_child(panel)
	var box := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.03, 0.05, 0.09, 0.8)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(16)
	box.add_theme_stylebox_override("panel", sb)
	box.position = Vector2(24, 24)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(box)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 3)
	box.add_child(v)
	hud = _text("", 22, Color("e8eef7"))
	v.add_child(hud)
	v.add_child(_text("Tools: bright working · dim idle · amber light: maintenance · red light: broken down", 15, Color("b8c4d6")))
	v.add_child(_text("Lots: white · hot lots orange · towers are lots waiting at a bay", 15, Color("b8c4d6")))
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 26)
	v.add_child(grid)
	for a in S["areas"]:
		var row := HBoxContainer.new()
		var r := ColorRect.new()
		r.color = Color(S["areas"][a]["colour"])
		r.custom_minimum_size = Vector2(13, 13)
		r.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		row.add_child(r)
		row.add_child(_text(S["areas"][a]["name"], 15, Color("d5deea")))
		grid.add_child(row)
	caption = _text("A gigafab-style layout of our own design on the SMT2020 model. Not a real fab. Support buildings drawn only; lots drawn larger than life.", 18, Color("8fa0b8"))
	caption.position = Vector2(30, 1040)
	panel.add_child(caption)
	legend = caption


func _apply_states_until(now: float) -> void:
	var st: Array = S["states"]
	while state_i < st.size() and float(st[state_i][0]) <= now:
		var e: Array = st[state_i]
		var i := int(e[1])
		var s := int(e[2])
		if tool_state[i] != s:
			tool_state[i] = s
			tools_mm.set_instance_color(i, _state_colour(i, s))
			var tb: Dictionary = S["tools"][i]
			if s >= 2:
				var p := w((tb["x0"] + tb["x1"]) / 2.0, (tb["y0"] + tb["y1"]) / 2.0, float(tb["h"]) + 1.6)
				beacons_mm.set_instance_transform(i, Transform3D(Basis(), p))
				beacons_mm.set_instance_color(i, Color(2.4, 1.5, 0.2) if s == 2 else Color(2.6, 0.35, 0.3))
			else:
				beacons_mm.set_instance_transform(i, Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO))
		state_i += 1


func _restart() -> void:
	t = S["from"]
	state_i = 0
	for i in cursor.size():
		cursor[i] = 0
	_apply_states_until(t)


func _lot_position(i: int, now: float) -> Variant:
	var k: Array = lot_keys[i]
	if now < float(k[0][0]) or now > float(k[k.size() - 1][0]):
		return null
	var c := cursor[i]
	while c + 1 < k.size() and float(k[c + 1][0]) <= now:
		c += 1
	cursor[i] = c
	var a: Array = k[c]
	if c + 1 >= k.size():
		return w(a[1], a[2], a[3])
	var b: Array = k[c + 1]
	var span: float = float(b[0]) - float(a[0])
	var u: float = 0.0 if span <= 0.0 else (now - float(a[0])) / span
	return w(lerp(float(a[1]), float(b[1]), u), lerp(float(a[2]), float(b[2]), u), lerp(float(a[3]), float(b[3]), u))


func _process(delta: float) -> void:
	if S.is_empty():
		return
	if shot != "":
		shot_at -= delta
		if shot_at <= 0.0:
			get_viewport().get_texture().get_image().save_png(shot)
			get_tree().quit()
			return
	if tour:
		_tour_step(delta)
	if not paused:
		t += delta * speed
		if t > float(S["to"]):
			if quit_after:
				get_tree().quit()
				return
			_restart()
	_apply_states_until(t)
	var moving := 0
	var waiting := 0
	var hidden := Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO)
	for i in lot_keys.size():
		var p = _lot_position(i, t)
		if p == null:
			lots_mm.set_instance_transform(i, hidden)
		else:
			lots_mm.set_instance_transform(i, Transform3D(Basis(), p))
			if p.y > 6.5:
				moving += 1
			else:
				waiting += 1
	var counts := [0, 0, 0, 0]
	for s in tool_state:
		counts[s] += 1
	var day := int(t / 1440.0)
	var hm := int(t) % 1440
	hud.text = "Fab Gym · simulated day %d, %02d:%02d   ×%d\nLots on the hoist %d · at tools or waiting %d\nTools working %d · idle %d · maintenance %d · broken down %d" % [day, hm / 60, hm % 60, int(speed * 60.0), moving, waiting, counts[0], counts[1], counts[2], counts[3]]


# ------------------------------------------------------------------ camera

const VIEWS := {
	1: [Vector3(376, 0, 0), -0.55, 0.62, 820.0],
	2: [Vector3(160, 0, 0), -0.25, 0.42, 260.0],
	3: [Vector3(350, 0, 0), 0.9, 0.35, 160.0],
	4: [Vector3(450, 0, 0), -0.6, 0.5, 220.0],
	5: [Vector3(376, 0, 0), 0.0, 1.5, 700.0],
}

# the tour: (seconds, pivot, yaw, pitch, distance), eased between
const TOUR := [
	[0.0, Vector3(376, 0, 0), 2.45, 0.78, 760.0],
	[8.0, Vector3(300, 0, 0), 2.75, 0.62, 560.0],
	[18.0, Vector3(120, 0, 0), 3.05, 0.55, 250.0],
	[28.0, Vector3(250, 0, 0), 2.85, 0.34, 190.0],
	[36.0, Vector3(345, 0, 0), 2.2, 0.36, 170.0],
	[44.0, Vector3(450, 0, 0), 3.5, 0.45, 210.0],
	[52.0, Vector3(400, 0, 0), 3.9, 0.85, 640.0],
	[60.0, Vector3(376, 0, 0), 4.05, 1.05, 700.0],
]


func _tour_step(delta: float) -> void:
	tour_t += delta
	var n := TOUR.size()
	if tour_t >= TOUR[n - 1][0]:
		tour_t = TOUR[n - 1][0]
	for i in n - 1:
		var a: Array = TOUR[i]
		var b: Array = TOUR[i + 1]
		if tour_t >= a[0] and tour_t <= b[0]:
			var u: float = (tour_t - a[0]) / (b[0] - a[0])
			u = u * u * (3.0 - 2.0 * u)
			pivot = (a[1] as Vector3).lerp(b[1], u)
			yaw = lerp(float(a[2]), float(b[2]), u)
			pitch = lerp(float(a[3]), float(b[3]), u)
			dist = lerp(float(a[4]), float(b[4]), u)
			break
	_place_camera()


var dragging := false
var panning := false


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton:
		if e.button_index == MOUSE_BUTTON_LEFT:
			dragging = e.pressed
		elif e.button_index == MOUSE_BUTTON_RIGHT or e.button_index == MOUSE_BUTTON_MIDDLE:
			panning = e.pressed
		elif e.button_index == MOUSE_BUTTON_WHEEL_UP:
			dist = max(20.0, dist * 0.9)
		elif e.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			dist = min(3000.0, dist * 1.1)
		tour = false
		_place_camera()
	elif e is InputEventMagnifyGesture:
		dist = clamp(dist / e.factor, 20.0, 3000.0)
		_place_camera()
	elif e is InputEventPanGesture:
		yaw -= e.delta.x * 0.02
		pitch = clamp(pitch + e.delta.y * 0.02, 0.05, 1.55)
		_place_camera()
	elif e is InputEventMouseMotion:
		if dragging:
			yaw -= e.relative.x * 0.005
			pitch = clamp(pitch + e.relative.y * 0.005, 0.05, 1.55)
			_place_camera()
		elif panning:
			_pan(-e.relative.x * dist * 0.0012, -e.relative.y * dist * 0.0012)
	elif e is InputEventKey and e.pressed:
		match e.keycode:
			KEY_SPACE:
				paused = not paused
			KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
				speed = min(speed * 2.0, 480.0)
			KEY_MINUS, KEY_KP_SUBTRACT:
				speed = max(speed / 2.0, 0.25)
			KEY_T:
				tour = not tour
				tour_t = 0.0
			KEY_H:
				panel.visible = not panel.visible
			KEY_R:
				_restart()
			KEY_W:
				_pan(0, -dist * 0.05)
			KEY_S:
				_pan(0, dist * 0.05)
			KEY_A:
				_pan(-dist * 0.05, 0)
			KEY_D:
				_pan(dist * 0.05, 0)
			KEY_1, KEY_2, KEY_3, KEY_4, KEY_5:
				var v: Array = VIEWS[int(e.keycode - KEY_0)]
				pivot = v[0]
				yaw = v[1]
				pitch = v[2]
				dist = v[3]
				tour = false
				_place_camera()


func _pan(dx: float, dz: float) -> void:
	var right := Vector3(cos(yaw), 0, -sin(yaw))
	var fwd := Vector3(-sin(yaw), 0, -cos(yaw))
	pivot += right * dx - fwd * dz
	_place_camera()
