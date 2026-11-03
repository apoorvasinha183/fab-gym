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


func setup(campus_data: Dictionary) -> void:
	fabs = campus_data["fabs"]
	clean_z = float(campus_data["heights"]["clean_z"])
	cinema = campus_data.get("cinema", {})


func floor_at(x: float, y: float) -> float:
	# plan point to the floor height: the clean floor inside a fab building, the cinema's steps, aisles and ramp, the
	# ground outside
	for f in fabs:
		if x >= float(f[0]) and x <= float(f[1]) and y >= float(f[2]) and y <= float(f[3]):
			return clean_z
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
		var back := follow.global_transform.basis.z.normalized()
		var want := follow.global_position + back * -4.5 + Vector3(0, 2.6, 0)
		var in_lift := not lift.is_empty() and g.x > float(lift[0]) and g.x < float(lift[3]) and -g.z > float(lift[1]) and -g.z < float(lift[4])
		var riding: bool = in_lift and ((st is Array and int(k) < st.size() and st[int(k)].get("ride", false)) or g.y > 1.0)
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
		elif floor_at(g.x, -g.z) > 1.0:
			# inside a fab: stand on the spine's middle line, a few metres back along it, above the tools
			want = Vector3(g.x - 7.0, g.y + 1.75, 0.0)
		global_position = global_position.lerp(want, clampf(dt * 2.0, 0.0, 1.0))
		var look := follow.global_position + Vector3(0, 1.6, 0) - back * -6.0
		var d := look - global_position
		yaw = lerp_angle(yaw, atan2(-d.x, -d.z), clampf(dt * 3.0, 0.0, 1.0))
		pitch = lerpf(pitch, atan2(d.y, Vector2(d.x, d.z).length()), clampf(dt * 3.0, 0.0, 1.0))
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
			global_position += dir.normalized() * speed * dt
		if not fly:
			global_position.y = floor_at(global_position.x, -global_position.z) + 1.65
	rotation = Vector3(0, yaw, 0)
	camera.rotation = Vector3(pitch, 0, 0)
