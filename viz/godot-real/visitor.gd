extends Node3D
## A Walk Through the Fab: the visitor's plan (res://data/visitor.json, from viz/visitor/plan.py)
## played live in the explore scene. A gigafab-style layout of our own design from the SMT2020 testbed;
## not a real fab. The run chose where he goes; this script only plays it back: his walk, his
## gaze, the camera over his shoulder, the fab clock and the cards with the run's numbers.
## The visitor, the rooms of the way in and the walkway are drawn only: he is not in the model and
## no number comes from him. He is the CC0 hazmat character (Quaternius, via Poly Pizza),
## recoloured as a cleanroom suit, its weapons never drawn.
##
## Keys in Visitor mode: V leave · Space pause · Left/Right back or on 5 s · R from the start

const PLAN := "res://data/visitor.json"
const MODEL := "res://data/hazmat.glb"
const BADGE := "A Walk Through the Fab · a gigafab-style layout of our own design, from the SMT2020 testbed · not a real fab · the visitor is drawn only"
const HEIGHT := 1.75
const WALK_FOOT := 2.35   # the walk clip's foot speed at the model's own size, m/s
const KEEP := ["Character_Hazmat", "Character_Hazmat_Head"]
const ARM := ["Shoulder", "UpperArm", "LowerArm"]

var main: Node3D
var P: Dictionary = {}
var path: Array = []
var camk: Array = []
var knots: Array = []
var cuts := {}
var dt := 0.125
var s := 0.0
var end_s := 0.0
var active := false
var paused := false
var last_t := -1.0

var who: Node3D            # turns with his body
var model: Node3D
var skel: Skeleton3D
var anim: AnimationPlayer
var scale_k := 1.0
var cur_anim := ""
var head_i := -1
var arm_l: Array = []
var arm_r: Array = []
var arm_down := {}         # left arm bone -> local rotation, standing
var suit_mats: Array = []  # [material, suit colour, street colour]
var suited := true
var card_title := ""
var badge: Label
var rooms_node: Node3D
var ring: MeshInstance3D
var ring_mat: StandardMaterial3D
const RING_COLOUR := {"breakdown": "ff4d4d", "maintenance": "ffb020", "queue": "4da3ff", "hot": "ffd23a", "hoist": "35d0e0"}


func setup(m: Node3D) -> bool:
	main = m
	var f := FileAccess.open(m.fab_dir + "visitor.json" if m.fab != "" else PLAN, FileAccess.READ)
	if f == null:
		return false
	P = JSON.parse_string(f.get_as_text())
	path = P["path"]
	camk = P["camera"]
	knots = P["clock"]
	dt = float(P["dt"])
	end_s = float(path[-1][0])
	for c in P["cuts"]:
		cuts[snappedf(float(c), 0.0001)] = true
	_rooms()
	_car()
	ring = MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = 0.55
	tm.outer_radius = 0.68
	ring.mesh = tm
	ring_mat = _mat("ffffff", 0.0, 0.4)
	ring_mat.emission_enabled = true
	ring_mat.emission_energy_multiplier = 2.5
	ring.material_override = ring_mat
	ring.visible = false
	add_child(ring)
	who = Node3D.new()
	who.name = "visitor"
	add_child(who)
	model = _model()
	if model != null:
		who.add_child(model)
		_fit()
	visible = false
	return true


# ---------------------------------------------------------------- drawn only: rooms, his car

func _mat(hex: String, metal := 0.0, rough := 0.6, alpha := 1.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(hex)
	m.albedo_color.a = alpha
	m.metallic = metal
	m.roughness = rough
	if alpha < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


func _box(parent: Node3D, m: Material, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> void:
	var mi := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = Vector3(absf(x1 - x0), absf(z1 - z0), absf(y1 - y0))
	mi.mesh = b
	mi.material_override = m
	mi.position = main.w((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
	parent.add_child(mi)


func _doors(r: Dictionary) -> Dictionary:
	## where his path crosses each side of a room: a door there
	var out := {"x0": [], "x1": [], "y0": [], "y1": []}
	for i in range(path.size() - 1):
		var a: Array = path[i]
		var b: Array = path[i + 1]
		if cuts.has(snappedf(float(b[0]), 0.0001)):
			continue
		for side in ["x0", "x1"]:
			var x: float = r[side]
			if (a[1] - x) * (b[1] - x) <= 0.0 and absf(b[1] - a[1]) > 1e-6:
				var y: float = a[2] + (b[2] - a[2]) * (x - a[1]) / (b[1] - a[1])
				if y > r["y0"] and y < r["y1"]:
					out[side].append(y)
		for side in ["y0", "y1"]:
			var y: float = r[side]
			if (a[2] - y) * (b[2] - y) <= 0.0 and absf(b[2] - a[2]) > 1e-6:
				var x: float = a[1] + (b[1] - a[1]) * (y - a[2]) / (b[2] - a[2])
				if x > r["x0"] and x < r["x1"]:
					out[side].append(x)
	return out


func _wall(parent: Node3D, m: Material, along_x: bool, at: float, lo: float, hi: float, z0: float, z1: float, gaps: Array) -> void:
	var cuts_at: Array = []
	for g in gaps:
		cuts_at.append([g - 0.65, g + 0.65])
	cuts_at.sort_custom(func(p, q): return p[0] < q[0])
	var x := lo
	var lintel := minf(z0 + 2.3, z1)
	for c in cuts_at:
		if c[0] > x:
			_seg(parent, m, along_x, at, x, minf(c[0], hi), z0, z1)
		if lintel < z1:
			_seg(parent, m, along_x, at, maxf(c[0], lo), minf(c[1], hi), lintel, z1)
		x = maxf(x, c[1])
	if x < hi:
		_seg(parent, m, along_x, at, x, hi, z0, z1)


func _seg(parent: Node3D, m: Material, along_x: bool, at: float, a: float, b: float, z0: float, z1: float) -> void:
	if b - a < 0.01:
		return
	if along_x:
		_box(parent, m, a, at - 0.04, z0, b, at + 0.04, z1)
	else:
		_box(parent, m, at - 0.04, a, z0, at + 0.04, b, z1)


func _rooms() -> void:
	rooms_node = Node3D.new()
	rooms_node.name = "visitor rooms"
	add_child(rooms_node)
	var floor_m := _mat("d9dde1", 0.1, 0.5)
	var panel := _mat("eef1f4", 0.1, 0.45)
	var glass := _mat("9ec3d8", 0.2, 0.08, 0.32)
	var steel := _mat("b8c0c8", 0.8, 0.3)
	var bench := _mat("5c6f88", 0.2, 0.5)
	for r in P["rooms"]:
		var x0: float = r["x0"]
		var x1: float = r["x1"]
		var y0: float = r["y0"]
		var y1: float = r["y1"]
		var z0: float = r["z0"]
		var z1: float = r["z1"]
		var k: String = r["kind"]
		var d := _doors(r)
		_box(rooms_node, floor_m, x0, y0, z0 - 0.08, x1, y1, z0)
		if k == "walkway":
			if r["name"] == "personnel bridge":
				_box(rooms_node, glass, x0, y0, z0, x1, y0 + 0.06, z0 + 1.05)
				_box(rooms_node, glass, x0, y1 - 0.06, z0, x1, y1, z0 + 1.05)
				_box(rooms_node, steel, x0, y0, z0 - 0.6, x1, y1, z0 - 0.08)
			continue
		var m: Material = panel
		if k == "bridge" or k == "lift" or r["name"] == "lobby":
			m = glass
		if r["name"] == "air shower":
			m = steel
		_wall(rooms_node, m, true, y0, x0, x1, z0, z1, d["y0"])
		_wall(rooms_node, m, true, y1, x0, x1, z0, z1, d["y1"])
		_wall(rooms_node, m, false, x0, y0, y1, z0, z1, d["x0"])
		_wall(rooms_node, m, false, x1, y0, y1, z0, z1, d["x1"])
		if k == "bridge":
			_box(rooms_node, steel, x0, y0, z1, x1, y1, z1 + 0.25)
			_box(rooms_node, steel, x0, y0, z0 - 0.6, x1, y1, z0 - 0.08)
		elif r["name"] == "gowning":
			# a bench and lockers along the west wall
			_box(rooms_node, bench, x0 + 0.3, y0 + 1.0, z0, x0 + 0.8, y1 - 1.0, z0 + 0.45)
			_box(rooms_node, panel, x0 + 0.05, y0 + 0.5, z0, x0 + 0.3, y1 - 0.5, z0 + 2.0)
		elif r["name"] == "air shower":
			for i in 6:
				var x := x0 + 0.2 + i * (x1 - x0 - 0.4) / 5.0
				_box(rooms_node, steel, x - 0.03, y0 + 0.05, z0 + 0.4, x + 0.03, y0 + 0.1, z1 - 0.3)
				_box(rooms_node, steel, x - 0.03, y1 - 0.1, z0 + 0.4, x + 0.03, y1 - 0.05, z1 - 0.3)


func _car() -> void:
	var c: Dictionary = P["car"]
	var n := Node3D.new()
	n.name = "visitor car"
	add_child(n)
	var x: float = c["x"]
	var y: float = c["y"]
	_box(n, _mat("2d4f86", 0.6, 0.25), x - 0.9, y - 2.25, 0.3, x + 0.9, y + 2.25, 1.0)
	_box(n, _mat("1e2a35", 0.5, 0.05), x - 0.8, y - 1.0, 1.0, x + 0.8, y + 1.2, 1.45)
	for dx in [-0.8, 0.8]:
		for dy in [-1.4, 1.4]:
			_box(n, _mat("141516", 0.0, 0.9), x + dx - 0.12, y + dy - 0.33, 0.0, x + dx + 0.12, y + dy + 0.33, 0.66)


# ---------------------------------------------------------------- the visitor

func _model() -> Node3D:
	var doc := GLTFDocument.new()
	var st := GLTFState.new()
	if doc.append_from_file(ProjectSettings.globalize_path(MODEL), st) != OK:
		push_error("no visitor model: run viz/godot-real/sync.sh")
		return null
	var root: Node3D = doc.generate_scene(st)
	var drop: Array = []
	for n in _all(root):
		if n is MeshInstance3D and not KEEP.has(String(n.name)):
			drop.append(n)
		if n is Skeleton3D:
			skel = n
		if n is AnimationPlayer:
			anim = n
	for n in drop:
		n.get_parent().remove_child(n)
		n.free()
	for n in _all(root):
		if n is MeshInstance3D:
			_recolour(n)
	if anim != null:
		anim.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	if skel != null:
		head_i = skel.find_bone("Head")
		for b in ARM:
			arm_l.append(skel.find_bone(b + ".L"))
			arm_r.append(skel.find_bone(b + ".R"))
	return root


func _all(n: Node) -> Array:
	var out := [n]
	for c in n.get_children():
		out += _all(c)
	return out


func _recolour(mi: MeshInstance3D) -> void:
	var head := String(mi.name).ends_with("Head")
	for i in mi.mesh.get_surface_count():
		var src: Material = mi.mesh.surface_get_material(i)
		var name := src.resource_name if src != null else ""
		var suit: String
		var street: String
		if name == "Hazmat_Main":
			suit = "eceff3"
			street = "34506e"   # a visitor's jacket before he gowns
		elif name == "Black":
			suit = "1b2733" if head else "7f8fb4"
			street = "1b2733" if head else "2b2f36"
		else:
			suit = "b8c0c8"
			street = "8a9097"
		var m := _mat(suit, 0.0, 0.55)
		if head and name == "Black":
			m.metallic = 0.6
			m.roughness = 0.1
		mi.set_surface_override_material(i, m)
		suit_mats.append([m, Color(suit), Color(street)])


func _fit() -> void:
	## scale him to 1.75 m, feet on the ground, facing his plan heading
	var lo := INF
	var hi := -INF
	for n in _all(model):
		if n is MeshInstance3D:
			var bb: AABB = n.global_transform * n.get_aabb()
			lo = minf(lo, bb.position.y)
			hi = maxf(hi, bb.end.y)
	if hi > lo:
		scale_k = HEIGHT / (hi - lo)
		model.scale = Vector3.ONE * scale_k
		model.position.y = -lo * scale_k


func height() -> float:
	var lo := INF
	var hi := -INF
	for n in _all(model):
		if n is MeshInstance3D:
			var bb: AABB = n.global_transform * n.get_aabb()
			lo = minf(lo, bb.position.y)
			hi = maxf(hi, bb.end.y)
	return hi - lo


func meshes() -> Array:
	var out: Array = []
	for n in _all(model):
		if n is MeshInstance3D:
			out.append(String(n.name))
	return out


# ---------------------------------------------------------------- playing

func start(at := 0.0) -> void:
	active = true
	visible = true
	paused = false
	s = at
	last_t = -1.0
	main.walking = false
	main.following = false
	main._set_cut(false)
	if badge == null:
		badge = main._text(BADGE, 17, Color("ffe7a8"))
		main.card_box.get_parent().add_child(badge)
		badge.anchor_top = 1.0
		badge.anchor_bottom = 1.0
		badge.offset_left = 26
		badge.offset_top = -74
		badge.offset_bottom = -48
	badge.visible = true
	# the card goes top right, clear of him
	main.card_box.anchor_top = 0.0
	main.card_box.anchor_bottom = 0.0
	main.card_box.grow_vertical = Control.GROW_DIRECTION_END
	main.card_box.offset_top = 24
	main.card_box.offset_bottom = 24
	apply(s, 0.0)


func stop() -> void:
	active = false
	visible = false
	if badge != null:
		badge.visible = false
	main.card_box.visible = false
	main.card_box.anchor_top = 1.0
	main.card_box.anchor_bottom = 1.0
	main.card_box.grow_vertical = Control.GROW_DIRECTION_BEGIN
	main.card_box.offset_top = 0
	main.card_box.offset_bottom = -24


func step(delta: float) -> void:
	if not paused:
		s += delta
		if s > end_s:
			s = 0.0
	apply(s, 0.0 if paused else delta)


func seek(by: float) -> void:
	s = clampf(s + by, 0.0, end_s)


func clock_at(x: float) -> float:
	for i in range(knots.size() - 1):
		var a: Array = knots[i]
		var b: Array = knots[i + 1]
		if x <= float(b[0]):
			return float(a[1]) + (float(b[1]) - float(a[1])) * (x - float(a[0])) / (float(b[0]) - float(a[0]))
	return float(knots[-1][1])


func _k(x: float) -> int:
	return clampi(int(floor(x / dt + 1e-6)), 0, path.size() - 1)


func pose_at(x: float) -> Array:
	## [plan x, y, z, body yaw, head yaw, pitch, moving]
	var k := _k(x)
	var a: Array = path[k]
	var b: Array = path[mini(k + 1, path.size() - 1)]
	var u := clampf((x - float(a[0])) / dt, 0.0, 1.0)
	if cuts.has(snappedf(float(b[0]), 0.0001)) or k + 1 >= path.size():
		u = 0.0
	var moving := Vector2(b[1] - a[1], b[2] - a[2]).length() / dt > 0.3
	return [lerpf(a[1], b[1], u), lerpf(a[2], b[2], u), lerpf(a[3], b[3], u),
		lerp_angle(a[4], b[4], u), lerp_angle(a[5], b[5], u), lerpf(a[6], b[6], u), moving]


func cam_at(x: float) -> Array:
	var k := clampi(_k(x), 0, camk.size() - 1)
	var a: Array = camk[k]
	var b: Array = camk[mini(k + 1, camk.size() - 1)]
	var u := clampf((x - float(a[0])) / dt, 0.0, 1.0)
	if a[7] != b[7] or cuts.has(snappedf(float(b[0]), 0.0001)):
		u = 0.0
	var out: Array = []
	for i in range(1, 7):
		out.append(lerpf(a[i], b[i], u))
	return out


func apply(x: float, delta: float) -> void:
	var p := pose_at(x)
	who.position = main.w(p[0], p[1], p[2])
	who.rotation = Vector3(0, float(p[3]) + PI / 2, 0)   # the model faces +Z
	var walk: bool = p[6]
	_animate(walk, x, delta)
	_head(wrapf(float(p[4]) - float(p[3]), -PI, PI), float(p[5]))
	var gowned := true
	for o in P["outfit"]:
		if x >= float(o[0]):
			gowned = o[1] == "suit"
	if gowned != suited:
		suited = gowned
		for e in suit_mats:
			e[0].albedo_color = e[1] if gowned else e[2]
	# the fab runs on his clock
	var t := clock_at(x)
	if t < main.t - 1e-9:
		main._reset_states()
	main.t = t
	main._apply_states_until(t)
	main._place_lots()
	# the camera
	var c := cam_at(x)
	main.player.global_position = main.w(c[0], c[1], c[2]) - Vector3(0, 1.6, 0)
	main._look(main.w(c[3], c[4], c[5]))
	main._aim()
	main.cam.fov = float(P["fov_v"])
	# a ring on the floor under what he is watching
	ring.visible = false
	for sg in P["sights"]:
		if x >= float(sg["arrive_s"]) - 1.0 and x <= float(sg["leave_s"]):
			var lk: Array = sg["look"]
			ring.position = main.w(lk[0], lk[1], main.CZ + 0.03)
			var pulse := 1.0 + 0.08 * sin(x * 5.0)
			ring.scale = Vector3(pulse, 1.0, pulse)
			var col := Color(RING_COLOUR.get(sg["kind"], "ffffff"))
			ring_mat.albedo_color = col
			ring_mat.emission = col
			ring.visible = true
	# the card
	card_title = ""
	var text := ""
	for cd in P["cards"]:
		if x >= float(cd["s0"]) and x <= float(cd["s1"]):
			card_title = cd["title"]
			text = cd["title"] + "\n" + "\n".join(cd["lines"]) + "\n" + cd["fab_time"]
	main.card.text = text
	main.card_box.visible = text != ""
	var stage := ""
	for st in P["stages"]:
		if x >= float(st["s0"]):
			stage = st["name"]
	var day := int(t / 1440.0)
	var hm := int(t) % 1440
	main.hud.text = "Visitor · %s · film %d:%02d of %d:%02d%s\nSimulated day %d, %02d:%02d · the fab clock runs ×60 while he walks, ×10 while he watches" % [
		stage, int(x) / 60, int(x) % 60, int(end_s) / 60, int(end_s) % 60, "  (paused)" if paused else "",
		day + 1, hm / 60, hm % 60]


func _animate(walk: bool, x: float, delta: float) -> void:
	if anim == null or skel == null:
		cur_anim = "walk" if walk else "idle"
		return
	var want := "walk" if walk else "idle"
	if want != cur_anim:
		cur_anim = want
		anim.play("CharacterArmature|Walk" if walk else "CharacterArmature|Idle", 0.2)
	if walk:
		# the clip's feet move at 2.35 m/s at its own size; he walks at the plan's speed
		anim.speed_scale = float(P["speed"]) / (WALK_FOOT * scale_k)
	else:
		anim.speed_scale = 1.0
	anim.advance(delta)
	if arm_down.is_empty():
		_learn_arms()
	if not walk:
		for i in range(arm_l.size()):
			if arm_l[i] >= 0 and arm_down.has(arm_l[i]):
				skel.set_bone_pose_rotation(arm_l[i], arm_down[arm_l[i]])
	_mirror_arms(walk)


func _learn_arms() -> void:
	## the clip's walk swings only the left arm, and its idle holds both out: learn the left arm
	## hanging (a quarter into the walk) to stand with, and copy the left arm onto the right
	var was := anim.current_animation
	anim.play("CharacterArmature|Walk")
	anim.seek(0.25, true)
	for b in arm_l:
		if b >= 0:
			arm_down[b] = skel.get_bone_pose_rotation(b)
	if was != "":
		anim.play(was)
	else:
		anim.stop()


func _mirror_arms(walk: bool) -> void:
	## the right arm mirrors the left half a stride later; across the model's own x
	if arm_r.has(-1) or arm_l.has(-1):
		return
	var sx := Basis(Vector3(-1, 0, 0), Vector3(0, 1, 0), Vector3(0, 0, 1))
	var done := {}
	for i in range(arm_l.size()):
		var gl := skel.get_bone_global_pose(arm_l[i])
		var gm := Transform3D(sx * gl.basis * sx, sx * gl.origin)
		var parent := skel.get_bone_parent(arm_r[i])
		var pg: Transform3D = done[parent] if done.has(parent) else skel.get_bone_global_pose(parent)
		var local := pg.affine_inverse() * gm
		skel.set_bone_pose_rotation(arm_r[i], local.basis.get_rotation_quaternion())
		done[arm_r[i]] = gm


func _head(rel_yaw: float, pitch: float) -> void:
	if skel == null or head_i < 0:
		return
	var parent := skel.get_bone_parent(head_i)
	var pg := skel.get_bone_global_pose(parent)
	var rest := skel.get_bone_rest(head_i)
	# turn the head about the skeleton's up axis and tip it about its side axis
	var up := (pg.basis.inverse() * Vector3.UP).normalized()
	var side := (pg.basis.inverse() * Vector3.RIGHT).normalized()
	var q := Quaternion(up, clampf(rel_yaw, -1.75, 1.75)) * Quaternion(side, -clampf(pitch, -0.6, 0.6))
	skel.set_bone_pose_rotation(head_i, q * rest.basis.get_rotation_quaternion())


# ---------------------------------------------------------------- the headless check

func run_check(out: String) -> void:
	start(0.0)
	var times: Array = []
	for st in P["stages"]:
		var a: float = st["s0"]
		var b: float = st["s1"]
		for u in [0.25, 0.6]:
			times.append(a + (b - a) * u)
	for c in P["cards"]:
		times.append((float(c["s0"]) + float(c["s1"])) / 2.0)
	for i in 12:
		times.append(end_s * (i + 0.5) / 12.0)
	var grid: Array = []
	for x in times:
		grid.append(snappedf(float(x), dt))
	grid.sort()
	var samples: Array = []
	var prev := 0.0
	for x in grid:
		s = x
		apply(x, maxf(x - prev, 0.0))
		prev = x
		var p := pose_at(x)
		var look: Vector3 = -main.cam.global_transform.basis.z
		samples.append({
			"s": x,
			"pos": main.plan(who.global_position),
			"body": wrapf(who.rotation.y - PI / 2, -PI, PI),
			"cam": main.plan(main.cam.global_position),
			"look": [look.x, -look.z, look.y],
			"t": main.t,
			"card": card_title,
			"anim": cur_anim,
		})
	var lamps: Array = []
	for i in main.tool_state.size():
		lamps.append(main.lamp_set[i])
	var report := {
		"seed": P["seed"],
		"rooms": P["rooms"].size(),
		"badge": BADGE,
		"model": {"meshes": meshes(), "height": height()},
		"samples": samples,
		"lamps": lamps,
	}
	var f := FileAccess.open(out, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	print("visitor check written: ", out)
