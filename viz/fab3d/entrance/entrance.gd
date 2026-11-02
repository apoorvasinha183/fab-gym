extends Node3D
## The way in (docs/FAB-3D.md, F9): the parking lot, the visitors' pavilion, the lift, gowning room P1-GW1 and its air
## shower, modelled in Blender from the campus data. This script only places what moves or speaks: the lift car rides
## with whoever stands in the lift, the air shower's jets, the signs, and two workers gowning up. The lift, rooms and
## fittings are where the permit set puts them; the lot, pavilion and looks are ours, assumed. From the SMT2020
## testbed; not a real fab.

var e: Dictionary
var car: Node3D
var rider: Node3D               # the guide; the car follows it while it stands in the lift
var lift: Array
var staff_scene: PackedScene = preload("res://staff/staff.tscn")
var doors := []                 # [leaf, closed y (plan), open y (plan), level ("ground" or "clean")]
const DOOR_SPEED := 0.8         # metres a second each leaf slides
const Looks := preload("res://looks.gd")


static func w(x: float, y: float, z: float) -> Vector3:
	return Vector3(x, z, -y)


func setup(entrance: Dictionary) -> void:
	e = entrance
	lift = e["permit"]["lift"]["box"]
	car = find_child("lift_car", true, false)
	Looks.dress(self, {"asphalt": Looks.pbr("asphalt_02", 4.0, Color(1, 1, 1), -1.0, "diff", true), "paving": Looks.pbr("concrete_pavement", 2.5, Color(1, 1, 1), -1.0, "diff", true),
			"kerb": Looks.pbr("brushed_concrete", 1.5), "grass": Looks.pbr("leafy_grass", 3.5, Color(0.42, 0.62, 0.3), -1.0, "grey", true),
			"floor": Looks.pbr("smooth_concrete_floor", 3.0), "mat": Looks.pbr("rubber_tiles", 1.0, Color(0.55, 0.7, 0.95))})
	_lift_doors()
	var s: Array = e["permit"]["air_shower"]["box"]
	var sx := (float(s[0]) + float(s[3])) / 2.0
	var sz := float(s[2]) + 1.25
	# jets from the north wall blow south (Godot +z), from the south wall north
	$jets_north.position = w(sx, float(s[4]) - 0.1, sz)
	$jets_south.position = w(sx, float(s[1]) + 0.1, sz)
	$jets_south.rotation.y = PI
	var pav: Array = e["assumed"]["pavilion"]
	var gd: Array = e["assumed"]["ground_door"]
	var mid := (float(gd[1]) + float(gd[4])) / 2.0
	_sign("Visitors", w(float(pav[0]) - 1.55, mid, float(pav[5]) - 0.06), -PI / 2, Color(0.12, 0.45, 0.85))
	var ed: Array = e["permit"]["entry_door"]["box"]
	_sign("Gowning", w((float(ed[0]) + float(ed[3])) / 2.0, float(ed[4]) + 0.12, float(ed[5]) + 0.25), PI, Color(0.2, 0.25, 0.3))
	_sign("Air shower", w(float(s[0]) - 0.02, (float(s[1]) + float(s[4])) / 2.0, float(s[5]) + 0.2), -PI / 2, Color(0.2, 0.25, 0.3))
	# a worker sitting on the bench pulling on boots, another taking a suit from the rack
	var b: Array = e["permit"]["bench"]["box"]
	var sit: Node3D = staff_scene.instantiate()
	add_child(sit)
	sit.position = w((float(b[0]) + float(b[3])) / 2.0, (float(b[1]) + float(b[4])) / 2.0 - 0.6, float(b[2]))
	sit.rotation.y = PI / 2
	sit.dress("operator", "Sitting_Idle_Loop")
	var r: Array = e["permit"]["rack"]["box"]
	var take: Node3D = staff_scene.instantiate()
	add_child(take)
	take.position = w(float(r[3]) + 0.45, (float(r[1]) + float(r[4])) / 2.0, float(r[2]))
	take.rotation.y = -PI / 2
	take.dress("engineer", "Interact")


func _lift_doors() -> void:
	# two steel leaves in each of the shaft's doorways (the ground one on the west, the clean-floor one on the east),
	# sliding apart into the wall when the car stands at that floor
	var x0 := float(lift[0])
	var x1 := float(lift[3])
	var mid := (float(lift[1]) + float(lift[4])) / 2.0
	var steel := StandardMaterial3D.new()
	steel.albedo_color = Color(0.72, 0.74, 0.77)
	steel.metallic = 0.6
	steel.roughness = 0.35
	for spec in [[x0 + 0.06, 0.0, "ground"], [x1 - 0.06, 7.5, "clean"]]:
		for side in [-1.0, 1.0]:
			var leaf := MeshInstance3D.new()
			var bm := BoxMesh.new()
			bm.size = Vector3(0.04, 2.38, 0.6)
			leaf.mesh = bm
			leaf.material_override = steel
			var closed: float = mid + float(side) * 0.3
			leaf.position = w(float(spec[0]), closed, float(spec[1]) + 1.19)
			add_child(leaf)
			doors.append([leaf, closed, mid + float(side) * 0.92, str(spec[2])])


func _sign(text: String, at: Vector3, yaw: float, col: Color) -> void:
	var l := Label3D.new()
	l.text = text
	l.font_size = 36
	l.pixel_size = 0.006
	l.outline_size = 0
	l.modulate = Color(1, 1, 1)
	l.position = at
	l.rotation.y = yaw
	var plate := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.12 * text.length() + 0.4, 0.34, 0.03)
	plate.mesh = bm
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	plate.material_override = m
	plate.position = Vector3(0, 0, -0.03)
	l.add_child(plate)
	add_child(l)


func in_lift(p: Vector3) -> bool:
	return p.x > float(lift[0]) and p.x < float(lift[3]) and -p.z > float(lift[1]) and -p.z < float(lift[4])


func jets(on: bool) -> void:
	$jets_north.emitting = on
	$jets_south.emitting = on


func _process(dt: float) -> void:
	if car and rider and in_lift(rider.global_position):
		car.position.y = clampf(rider.global_position.y - 0.1, 0.0, 7.5)
	if car:
		var at_ground := car.position.y < 0.05
		var at_clean := car.position.y > 7.35
		for d in doors:
			var open: bool = at_ground if d[3] == "ground" else at_clean
			var leaf: MeshInstance3D = d[0]
			var want: float = -(float(d[2]) if open else float(d[1]))
			leaf.position.z = move_toward(leaf.position.z, want, DOOR_SPEED * dt)
