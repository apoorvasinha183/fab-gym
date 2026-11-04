extends Node3D
## The visitor (docs/FAB-3D.md): walk with W A S D on the fab's clean floor or the ground outside, hold Shift to hurry,
## F to fly (E up, Q down), the right mouse button held to look. While the guide leads, the camera follows it instead.
## From the SMT2020 testbed; not a real fab.

var yaw := 0.0
var pitch := -0.15
var fly := false
var roaming := true
var follow: Node3D = null
var fabs: Array = []
var clean_z := 7.5
var lift: Array = []          # the lift's box [x0, y0, z0, x1, y1, z1] in plan metres; the camera rides inside it
@onready var camera: Camera3D = $camera


var cinema: Dictionary = {}
var cin_floor: Dictionary = {}  # the cinema's floor map, cast down onto the built model (data/cinema-built.json)
var _cm := PackedInt32Array()
var lift_car: Node3D
var input_locked := false
var seated := false             # in a cinema seat: the camera stays at the seat's eye point, the mouse still looks
var seat_eye := Vector3.ZERO
var _dir_x := 1.0              # which way along the fab the guide is walking (+1 east, -1 west), so the camera stays behind him
var _trail: Array = []          # where the guide has walked lately, newest last; the camera keeps to his path
var _camera_body := SphereShape3D.new()
var _body := CapsuleShape3D.new()
const KNEE := 0.5               # the body clears anything lower than this over the floor (steps, tiers, seat pans)
# A walk the visitor takes on their own (main.gd --explore): floor points to walk to, some with a spot to stop and look
# at. Any of W A S D takes over, and the walk ends.
signal autopilot_at(w: Dictionary)
signal autopilot_done
var autopilot: Array = []
var autopilot_speed := 3.2
var _ap_hold := 0.0
var _ap_clock := 0.0
var _ap_from := Vector3.ZERO


func _init() -> void:
	_camera_body.radius = 0.18
	_body.radius = 0.2
	_body.height = 1.2


func move(m: Vector3) -> void:
	# walk, sliding along whatever is solid (solid.gd): walls, rails, seat backs, benches, tools
	var p := global_position
	var space := get_world_3d().direct_space_state
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = _body
	q.transform = Transform3D(Basis(), Vector3(p.x, floor_at(p.x, -p.z) + KNEE + _body.height / 2.0, p.z))
	if not space.intersect_shape(q, 1).is_empty():
		global_position += m        # already inside something: let the visitor walk out of it
		return
	for step in [m, Vector3(m.x, 0.0, 0.0), Vector3(0.0, 0.0, m.z)]:
		if step.length() < 1e-5:
			continue
		q.motion = step
		var r := space.cast_motion(q)
		if r[0] >= 1.0:
			global_position += step
			return
	q.motion = m
	global_position += m * maxf(space.cast_motion(q)[0] - 0.02, 0.0)


func _trail_point(back_m: float) -> Vector3:
	# the point on the guide's path this far behind him
	var left := back_m
	for k in range(_trail.size() - 1, 0, -1):
		var a: Vector3 = _trail[k]
		var b: Vector3 = _trail[k - 1]
		var d := a.distance_to(b)
		if d >= left:
			return a.lerp(b, left / d)
		left -= d
	return _trail[0] if not _trail.is_empty() else global_position


func setup(campus_data: Dictionary) -> void:
	fabs = campus_data["fabs"]
	clean_z = float(campus_data["heights"]["clean_z"])
	cinema = campus_data.get("cinema", {})
	var path := "res://data/cinema-built.json"
	if FileAccess.file_exists(path):
		var built = JSON.parse_string(FileAccess.get_file_as_string(path))
		if built is Dictionary and built.has("floor"):
			cin_floor = built["floor"]
			_cm = PackedInt32Array(cin_floor["cm"])


func in_fab(x: float, y: float) -> bool:
	for f in fabs:
		if x >= float(f[0]) and x <= float(f[1]) and y >= float(f[2]) and y <= float(f[3]):
			return true
	return false


func in_cinema(x: float, y: float) -> bool:
	if cin_floor.is_empty():
		return false
	var o: Array = cin_floor["origin"]
	var st := float(cin_floor["step"])
	return x >= float(o[0]) and y >= float(o[1]) and x <= float(o[0]) + st * (int(cin_floor["nx"]) - 1) \
			and y <= float(o[1]) + st * (int(cin_floor["ny"]) - 1)


func sit(eye: Vector3, facing: float) -> void:
	seated = true
	seat_eye = eye
	follow = null
	roaming = true
	fly = false
	yaw = facing
	pitch = -0.06


func glide(to: Vector3, to_yaw: float, to_pitch: float, secs: float) -> void:
	# an eased move to a spot and a view, then the visitor walks on their own from there
	follow = null
	roaming = false
	var t := create_tween().set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT).set_parallel()
	t.tween_property(self, "global_position", to, secs)
	t.tween_property(self, "yaw", yaw + wrapf(to_yaw - yaw, -PI, PI), secs)
	t.tween_property(self, "pitch", to_pitch, secs)
	t.chain().tween_callback(func() -> void: roaming = true)


func stand() -> void:
	seated = false
	_trail.clear()


func floor_at(x: float, y: float, eye_y: float = NAN) -> float:
	# plan point to the floor height: the clean floor inside a fab building, the cinema's steps, aisles and ramp, the
	# ground outside
	if in_fab(x, y):
		# The entrance block has two floors at the same plan point. Keep the visitor
		# on their current level; the car supplies its actual moving floor in the shaft.
		if not lift.is_empty() and x >= float(lift[0]) and x <= float(lift[3]) and y >= float(lift[1]) and y <= float(lift[4]) and is_instance_valid(lift_car):
			return lift_car.position.y + 0.1
		if x < 0.0:
			var level_y := global_position.y if is_nan(eye_y) else eye_y
			return clean_z if level_y > clean_z * 0.5 else 0.1
		return clean_z
	if in_cinema(x, y):
		# the top of the built floor under the point (steps, aisles, ramp, stair, projection room)
		var o: Array = cin_floor["origin"]
		var st := float(cin_floor["step"])
		var i := int(round((x - float(o[0])) / st))
		var j := int(round((y - float(o[1])) / st))
		var c := _cm[j * int(cin_floor["nx"]) + i]
		return float(c) / 100.0 if c >= 0 else 0.1
	if not cinema.is_empty():
		var h: Array = cinema["hall"]
		if x >= float(h[0]) and x <= float(h[2]) and y >= float(h[1]) and y <= float(h[3]):
			for fl in cinema["floors"]:
				if x >= float(fl[0]) and x < float(fl[1]):
					return 0.04 + float(fl[2])
			return 0.06
		var r: Dictionary = cinema["ramp"]
		var b: Array = r["box"]
		if x >= float(b[0]) and x <= float(b[2]) and y >= float(b[1]) and y <= float(b[3]):
			# up from the east end: a landing, then runs at 1 in 12 with landings between
			var d := float(b[2]) - x
			var land := float(r["landing_m"])
			var run := float(r["run_m"])
			var each := float(r["rise"]) / float(r["runs"])
			var z := 0.0
			d -= land
			for k in int(r["runs"]):
				if d <= 0.0:
					break
				z += each * clampf(d / run, 0.0, 1.0)
				d -= run + land
			return 0.06 + z
	return 0.1


func place(plan_x: float, plan_y: float, facing: float = 0.0) -> void:
	global_position = Vector3(plan_x, floor_at(plan_x, plan_y) + 1.65, -plan_y)
	yaw = facing


func controls_blocked() -> bool:
	var focus := get_viewport().gui_get_focus_owner()
	return input_locked or focus is LineEdit or focus is TextEdit


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _unhandled_input(e: InputEvent) -> void:
	if controls_blocked():
		return
	if e is InputEventKey and e.pressed and e.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if e is InputEventMouseButton and e.button_index == MOUSE_BUTTON_RIGHT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if e.pressed else Input.MOUSE_MODE_VISIBLE
	elif e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= e.relative.x * 0.0025
		pitch = clampf(pitch - e.relative.y * 0.0025, -1.45, 1.45)
	elif e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_F and roaming and not seated:
		fly = not fly


func _process(dt: float) -> void:
	if follow and not roaming:
		# behind and above the guide, looking past it
		var g := follow.global_position
		var st = follow.get("stops")
		var k = follow.get("i")
		if follow.get("mode") == "talk" and st is Array and int(k) < st.size() and st[int(k)].get("face_viewer", false):
			# the guide has turned to talk to the visitor: hold still and look at its face
			var dl := g + Vector3(0, 1.55, 0) - global_position
			yaw = lerp_angle(yaw, atan2(-dl.x, -dl.z), clampf(dt * 3.0, 0.0, 1.0))
			pitch = lerpf(pitch, atan2(dl.y, Vector2(dl.x, dl.z).length()), clampf(dt * 3.0, 0.0, 1.0))
			rotation = Vector3(0, yaw, 0)
			camera.rotation = Vector3(pitch, 0, 0)
			return
		if _trail.is_empty() or (_trail[-1] as Vector3).distance_to(g) > 0.25:
			_trail.append(g)
			if _trail.size() > 80:
				_trail.pop_front()
		var device: Dictionary = {}
		if follow.get("mode") == "talk" and st is Array and int(k) < st.size():
			device = st[int(k)].get("device", {})
		var back := follow.global_transform.basis.z.normalized()
		var want := follow.global_position + back * -4.5 + Vector3(0, 2.6, 0)
		var in_lift := not lift.is_empty() and g.x > float(lift[0]) and g.x < float(lift[3]) and -g.z > float(lift[1]) and -g.z < float(lift[4])
		var riding: bool = in_lift      # in the car with him from the moment he steps in, riding or not
		if riding:
			# in the car with him: at the door side, eye height, fixed to the car (no lag, so it cannot drift into the
			# shaft), looking at his face across the car
			global_position = Vector3(float(lift[0]) + 0.3, g.y + 1.45, -(float(lift[1]) + float(lift[4])) / 2.0)
			var dl := g + Vector3(0, 1.7, 0) - global_position
			yaw = lerp_angle(yaw, atan2(-dl.x, -dl.z), clampf(dt * 5.0, 0.0, 1.0))
			pitch = lerpf(pitch, atan2(dl.y, Vector2(dl.x, dl.z).length()), clampf(dt * 5.0, 0.0, 1.0))
			rotation = Vector3(0, yaw, 0)
			camera.rotation = Vector3(pitch, 0, 0)
			return
		if (g.y > 1.0 and g.x < 1.7) or (g.y < 1.0 and g.x > -20.0 and g.x < 0.0):
			# the lift lobby, the gowning room, the air shower, the strip behind the first bay: close behind, eye height
			want = follow.global_position + back * -2.2 + Vector3(0, 1.55, 0)
		elif in_cinema(g.x, -g.z):
			# the cinema's lobby, ramp and hall: on his own path, a few steps behind, at eye height (so through the
			# doors he went through)
			want = _trail_point(2.6) + Vector3(0, 1.6, 0)
		elif in_fab(g.x, -g.z):
			# inside a fab: stand on the spine's middle line, a few metres back along it (behind him, whichever way he
			# walks; it flips only once he has clearly turned), above the tools
			var dx := g.x - _trail_point(4.0).x
			if absf(dx) > 2.5:
				_dir_x = signf(dx)
			want = Vector3(g.x - 7.0 * _dir_x, g.y + 1.75, 0.0)
		if not device.is_empty():
			# Stay in the clear spine and turn into the bay while Lou explains its device.
			want = Vector3(g.x, g.y + 1.8, 0.0)
		var candidate := global_position.lerp(want, 1.0 - exp(-dt * 2.0))
		# Set height first, then sweep a small volume: a ray misses near-plane corners.
		candidate.y = maxf(candidate.y, floor_at(candidate.x, -candidate.z, g.y + 1.65) + 1.3)
		var head := g + Vector3(0, 1.5, 0)
		var probe := PhysicsShapeQueryParameters3D.new()
		probe.shape = _camera_body
		probe.transform = Transform3D(Basis(), head)
		probe.motion = candidate - head
		var fraction := get_world_3d().direct_space_state.cast_motion(probe)[0]
		global_position = head.lerp(candidate, maxf(0.0, fraction - 0.01) if fraction < 1.0 else 1.0)
		var look := follow.global_position + Vector3(0, 1.6, 0) - back * -6.0
		if in_fab(g.x, -g.z):
			look = Vector3(g.x + 6.0 * _dir_x, g.y + 1.6, g.z)     # down the spine the way he walks, not swinging at corners
		if not device.is_empty():
			look = device["target"]
		var d := look - global_position
		yaw = lerp_angle(yaw, atan2(-d.x, -d.z), clampf(dt * 3.0, 0.0, 1.0))
		pitch = lerpf(pitch, atan2(d.y, Vector2(d.x, d.z).length()), clampf(dt * 3.0, 0.0, 1.0))
	elif seated:
		global_position = seat_eye
	elif roaming and not autopilot.is_empty() and not _keys_down():
		_autopilot(dt)
		var floor_y := floor_at(global_position.x, -global_position.z) + 1.65
		global_position.y = floor_y if floor_y > global_position.y else lerpf(global_position.y, floor_y, clampf(dt * 10.0, 0.0, 1.0))
	elif roaming and not controls_blocked():
		if not autopilot.is_empty():
			autopilot.clear()       # the visitor took over
			autopilot_done.emit()
		var dir := Vector3.ZERO
		var bz := Basis(Vector3.UP, yaw)
		if Input.is_key_pressed(KEY_W):
			dir -= bz.z
		if Input.is_key_pressed(KEY_S):
			dir += bz.z
		if Input.is_key_pressed(KEY_A):
			dir -= bz.x
		if Input.is_key_pressed(KEY_D):
			dir += bz.x
		var speed := 10.0 if Input.is_key_pressed(KEY_SHIFT) else 4.0
		if fly:
			speed *= 3.0
			if Input.is_key_pressed(KEY_E):
				dir.y += 1.0
			if Input.is_key_pressed(KEY_Q):
				dir.y -= 1.0
		if dir.length() > 0:
			if fly:
				global_position += dir.normalized() * speed * dt
			else:
				move(dir.normalized() * speed * dt)
		if not fly:
			# up a step at once (so the eye never dips under it), down a step eased
			var want_y := floor_at(global_position.x, -global_position.z) + 1.65
			global_position.y = want_y if want_y > global_position.y else lerpf(global_position.y, want_y, clampf(dt * 10.0, 0.0, 1.0))
	rotation = Vector3(0, yaw, 0)
	camera.rotation = Vector3(pitch, 0, 0)


func _keys_down() -> bool:
	return not controls_blocked() and (Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_A)
			or Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_D))


func _look_toward(target: Vector3, dt: float, rate: float) -> void:
	var d := target - global_position
	yaw = lerp_angle(yaw, atan2(-d.x, -d.z), clampf(dt * rate, 0.0, 1.0))
	pitch = lerpf(pitch, clampf(atan2(d.y, Vector2(d.x, d.z).length()), -0.6, 0.4), clampf(dt * rate, 0.0, 1.0))


func _autopilot(dt: float) -> void:
	# walk the way a person does: the head turns first, the feet follow, slower round corners, a pause to look
	var w: Dictionary = autopilot[0]
	var at: Vector3 = w["at"]
	var to := Vector3(at.x - global_position.x, 0.0, at.z - global_position.z)
	var dist := to.length()
	if dist < 0.5:
		if w.has("look") and _ap_hold < float(w.get("hold", 0.0)):
			if _ap_hold == 0.0:
				autopilot_at.emit(w)
			_ap_hold += dt
			_look_toward(w["look"], dt, 2.0)
			return
		_ap_hold = 0.0
		autopilot.pop_front()
		_ap_clock = 0.0
		if autopilot.is_empty():
			autopilot_done.emit()
		return
	# look a little ahead along the path, so corners are turned smoothly
	var ahead := at
	if dist < 3.0 and autopilot.size() > 1:
		ahead = at.lerp(autopilot[1]["at"], 1.0 - dist / 3.0)
	var heading := atan2(-(ahead.x - global_position.x), -(ahead.z - global_position.z))
	yaw = lerp_angle(yaw, heading, clampf(dt * 2.2, 0.0, 1.0))
	pitch = lerpf(pitch, -0.06, clampf(dt * 1.5, 0.0, 1.0))
	var off := absf(wrapf(heading - yaw, -PI, PI))
	var speed := autopilot_speed * clampf(1.3 - off, 0.15, 1.0)
	# the route is already on the walkable floor (the baked navigation mesh), so it is followed exactly
	global_position += to.normalized() * minf(speed * dt, dist)
	# stuck against something for two seconds: give that point up
	_ap_clock += dt
	if _ap_clock > 2.0:
		if global_position.distance_to(_ap_from) < 0.4:
			print("fab3d: explore skipped a point it could not reach at ", Vector2(at.x, -at.z))
			autopilot.pop_front()
			if autopilot.is_empty():
				autopilot_done.emit()
		_ap_clock = 0.0
		_ap_from = global_position
