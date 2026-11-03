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
var seated := false             # in a cinema seat: the camera stays at the seat's eye point, the mouse still looks
var seat_eye := Vector3.ZERO
var _trail: Array = []          # where the guide has walked lately, newest last; the camera keeps to his path
var _body := CapsuleShape3D.new()
const KNEE := 0.5               # the body clears anything lower than this over the floor (steps, tiers, seat pans)


func _init() -> void:
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


func floor_at(x: float, y: float) -> float:
	# plan point to the floor height: the clean floor inside a fab building, the cinema's steps, aisles and ramp, the
	# ground outside
	if in_fab(x, y):
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


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton and e.button_index == MOUSE_BUTTON_RIGHT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if e.pressed else Input.MOUSE_MODE_VISIBLE
	elif e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= e.relative.x * 0.0025
		pitch = clampf(pitch - e.relative.y * 0.0025, -1.45, 1.45)
	elif e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_F and roaming:
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
			# inside a fab: stand on the spine's middle line, a few metres back along it, above the tools
			want = Vector3(g.x - 7.0, g.y + 1.75, 0.0)
		global_position = global_position.lerp(want, clampf(dt * 2.0, 0.0, 1.0))
		# nothing solid between his head and the camera: if a wall is in the way, come in front of it
		var head := g + Vector3(0, 1.5, 0)
		var ray := PhysicsRayQueryParameters3D.create(head, global_position)
		var hit := get_world_3d().direct_space_state.intersect_ray(ray)
		if not hit.is_empty():
			global_position = hit["position"] + (head - hit["position"]).normalized() * 0.3
		# never below eye height over whatever floor is under the camera (steps, the ramp, the stadium)
		global_position.y = maxf(global_position.y, floor_at(global_position.x, -global_position.z) + 1.3)
		var look := follow.global_position + Vector3(0, 1.6, 0) - back * -6.0
		var d := look - global_position
		yaw = lerp_angle(yaw, atan2(-d.x, -d.z), clampf(dt * 3.0, 0.0, 1.0))
		pitch = lerpf(pitch, atan2(d.y, Vector2(d.x, d.z).length()), clampf(dt * 3.0, 0.0, 1.0))
	elif seated:
		global_position = seat_eye
	elif roaming:
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
