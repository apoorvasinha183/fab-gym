extends Control
## The replay (docs/REPLAY.md): two copies of one campus from the SMT2020 testbed, a gigafab-style layout of our
## own design and not a real fab. Same seed, same hours: today's rule on the left, a written rule on the
## right, on one clock and one camera. The panels count from the window's start, from viz/replay.py's series.
##
## Keys: Space pause, + and - speed, arrows orbit, PageUp/PageDown height, W the watched group,
## 1 the campus, R restart.
## Film:   godot --path viz/godot-real --write-movie OUT.avi res://compare.tscn -- --speed 6 --orbit
## Check:  godot --headless --path viz/godot-real res://compare.tscn -- --compare-check OUT.json

const REPLAY := "res://data/replay/replay.json"
const KEYS := "Space pause · +/- speed · arrows orbit · PageUp/PageDown height · W watched group · 1 campus · R restart"

@onready var sides: Array = [$Rows/Sides/Left/View/Port/Fab, $Rows/Sides/Right/View/Port/Fab]
@onready var heads: Array = [$Rows/Sides/Left/Head, $Rows/Sides/Right/Head]
@onready var panels: Array = [$Rows/Sides/Left/Panel, $Rows/Sides/Right/Panel]
@onready var title: Label = $Rows/Title
@onready var foot: Label = $Rows/Foot

var R: Dictionary
var t := 0.0
var speed := 2.0          # fab minutes per real second
var paused := false
var yaw := deg_to_rad(-30.0)
var tilt := deg_to_rad(28.0)
var dist := 38.0
var focus := Vector3.ZERO  # world space
var watch_at := Vector3.ZERO
var campus_at := Vector3.ZERO
var tags: Array = []       # the floating queue count over the watched group, one per side
var orbit := false        # turn slowly round the watched group (for films)


func _ready() -> void:
	if not FileAccess.file_exists(REPLAY):
		push_error("no replay: run viz/replay.py RULE.rs --name NAME --copy from the repo root")
		get_tree().quit(1)
		return
	R = JSON.parse_string(FileAccess.open(REPLAY, FileAccess.READ).get_as_text())
	var f0: Dictionary = sides[0].S
	t = float(R["from"])
	var at: Array = R["watch"]["at"]
	watch_at = sides[0].w(float(at[0]), float(at[1]), sides[0].CZ)
	var g: Dictionary = f0["ground"]
	campus_at = sides[0].w((float(g["x0"]) + float(g["x1"])) / 2.0, 0.0, 0.0)
	focus = watch_at
	for s in sides:
		_ring(s)
		s._set_cut(true)   # roofs away, so the camera sees the clean floor
	var rule: Dictionary = R["rule"]
	heads[0].text = "Today's rule"
	heads[1].text = rule["name"] + ("  (hand-written)" if rule["hand_written"] else "  (written by the model)")
	var score: String = rule["card"] if rule["card"] != null else (
		"This rule is not scored on the held-out seeds: the counts above are one seed, one run, not an effect.")
	foot.text = "%s\nThe replay runs the campus layout's shop; a card's score is from the SMT2020 testbed with its own transport times. Watched: %s, %s.\n%s" % [
		score, R["watch"]["name"], R["watch"]["why"], KEYS]
	var args := OS.get_cmdline_user_args()
	var si := args.find("--speed")
	if si >= 0:
		speed = float(args[si + 1])
	orbit = args.has("--orbit")
	var ci := args.find("--compare-check")
	if ci >= 0:
		_check.call_deferred(args[ci + 1])
		return
	_apply()


func _ring(side: Node3D) -> void:
	# a glowing outline round the watched group's tools, on the clean floor
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color("ffb020")
	mat.emission_enabled = true
	mat.emission = Color("ffb020")
	mat.emission_energy_multiplier = 1.6
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var bx = R["watch"].get("box")
	var x0: float
	var y0: float
	var x1: float
	var y1: float
	if bx == null:
		var at: Array = R["watch"]["at"]
		x0 = float(at[0]) - 6.0
		x1 = float(at[0]) + 6.0
		y0 = float(at[1]) - 6.0
		y1 = float(at[1]) + 6.0
	else:
		x0 = float(bx[0]) - 1.2
		y0 = float(bx[1]) - 1.2
		x1 = float(bx[2]) + 1.2
		y1 = float(bx[3]) + 1.2
	var z: float = side.CZ + 0.06
	var bars := [[x0, y0, x1, y0], [x0, y1, x1, y1], [x0, y0, x0, y1], [x1, y0, x1, y1]]
	for e in bars:
		var a: Vector3 = side.w(e[0], e[1], z)
		var b: Vector3 = side.w(e[2], e[3], z)
		var m := BoxMesh.new()
		m.size = Vector3(maxf(absf(b.x - a.x), 0.35), 0.08, maxf(absf(b.z - a.z), 0.35))
		m.material = mat
		var mi := MeshInstance3D.new()
		mi.mesh = m
		mi.position = (a + b) / 2.0
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		side.add_child(mi)
	var tag := Label3D.new()
	tag.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	tag.no_depth_test = true
	tag.fixed_size = true
	tag.pixel_size = 0.0012
	tag.font_size = 30
	tag.outline_size = 10
	tag.modulate = Color("ffd27a")
	tag.outline_modulate = Color(0.05, 0.05, 0.07, 0.9)
	tag.position = side.w((x0 + x1) / 2.0, (y0 + y1) / 2.0, z + 6.0)
	side.add_child(tag)
	tags.append(tag)


func _index(now: float) -> int:
	var ts: Array = R["series"]["t"]
	var k := 0
	for i in ts.size():
		if float(ts[i]) <= now + 1e-6:
			k = i
	return k


func _counts(now: float) -> Array:
	var k := _index(now)
	var out := []
	for side in ["today", "rule"]:
		var s: Dictionary = R["series"][side]
		out.append({"moves": int(s["moves"][k]), "wait": float(s["wait_lot_hours"][k]), "queue": int(s["queue"][k])})
	return out


func _clock(now: float) -> String:
	var day := int(now / 1440.0)
	var hm := int(now) % 1440
	return "simulated day %d, %02d:%02d" % [day + 1, hm / 60, hm % 60]


func _apply() -> void:
	for s in sides:
		s.set_time(t)
	var off := Vector3(sin(yaw) * cos(tilt), sin(tilt), cos(yaw) * cos(tilt)) * dist
	for s in sides:
		s.pose(focus + off, focus, 50.0)
	var c := _counts(t)
	var w: Dictionary = R["watch"]
	var since := _clock(float(R["from"]))
	for i in 2:
		var q: int = c[i]["queue"]
		var txt := "Moves since %s: %d    Lot-hours waited: %.0f\nQueue at %s: %d %s" % [
			since, c[i]["moves"], c[i]["wait"], w["name"], q, "lot" if q == 1 else "lots"]
		if i == 1:
			txt += "    (today %+d moves, %+.0f lot-hours)" % [c[1]["moves"] - c[0]["moves"], c[1]["wait"] - c[0]["wait"]]
		panels[i].text = txt
		if i < tags.size():
			tags[i].text = "%s: %d waiting" % [w["name"], q]
	title.text = "Same campus, same seed (%d), %s, ×%d%s · from the SMT2020 testbed · not a real fab" % [
		int(R["seed"]), _clock(t), int(round(speed * 60.0)), "  (paused)" if paused else ""]


func _process(delta: float) -> void:
	if R.is_empty():
		return
	if orbit:
		yaw += delta * 0.06
	if not paused:
		t += delta * speed
		if t > float(R["to"]):
			t = float(R["from"])
	_apply()


func _unhandled_input(e: InputEvent) -> void:
	if not (e is InputEventKey and e.pressed):
		return
	match e.keycode:
		KEY_SPACE:
			paused = not paused
		KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
			speed = minf(speed * 2.0, 64.0)
		KEY_MINUS, KEY_KP_SUBTRACT:
			speed = maxf(speed / 2.0, 0.125)
		KEY_LEFT:
			yaw -= deg_to_rad(10.0)
		KEY_RIGHT:
			yaw += deg_to_rad(10.0)
		KEY_UP:
			tilt = minf(tilt + deg_to_rad(5.0), deg_to_rad(85.0))
		KEY_DOWN:
			tilt = maxf(tilt - deg_to_rad(5.0), deg_to_rad(8.0))
		KEY_PAGEUP:
			dist = minf(dist * 1.25, 1500.0)
		KEY_PAGEDOWN:
			dist = maxf(dist / 1.25, 12.0)
		KEY_W:
			focus = watch_at
			dist = 38.0
		KEY_1:
			focus = campus_at
			dist = 700.0
		KEY_R:
			t = float(R["from"])


func _check(out: String) -> void:
	var a := float(R["from"])
	var b := float(R["to"])
	var steps := []
	for k in 7:
		t = a + (b - a) * float(k) / 6.0 + (3.0 if k < 6 else 0.0)
		if k == 3:
			yaw += 0.7
			dist = 300.0
		_apply()
		var cams := []
		var panel := []
		var c := _counts(t)
		for i in 2:
			var x: Transform3D = sides[i].cam.global_transform
			cams.append([x.origin.x, x.origin.y, x.origin.z, x.basis.x.x, x.basis.x.y, x.basis.x.z,
				x.basis.y.x, x.basis.y.y, x.basis.y.z, x.basis.z.x, x.basis.z.y, x.basis.z.z])
			panel.append({"moves": c[i]["moves"], "queue": c[i]["queue"]})
		steps.append({"t": [sides[0].t, sides[1].t], "cam": cams, "panel": panel})
	var report := {
		"tools": [sides[0].tool_state.size(), sides[1].tool_state.size()],
		"steps": steps,
		"text": [title.text, heads[0].text, heads[1].text, panels[0].text, panels[1].text, foot.text],
	}
	var f := FileAccess.open(out, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	print("compare check written: ", out)
	get_tree().quit()
