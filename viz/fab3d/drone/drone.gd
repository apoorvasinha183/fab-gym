extends Node3D
## The opening flight over the campus (docs/FAB-3D.md, F10). The camera flies a Catmull-Rom curve through the keys in
## the campus data (the same curve the tests check), its gaze eased between the keys' look points; Lou's lines go to
## the text window as their keys pass, and each building's label pops up as the flight reaches it. Space skips it.
## From the SMT2020 testbed; not a real fab.

signal line(text: String)
signal done

const FONT := preload("res://ui/fonts/kenpixel.ttf")
const NAMES := {"cinema": "THE CINEMA", "utility yard": "UTILITY YARD", "bridge": "THE BRIDGE",
		"phase 2": "PHASE 2 - BACK END", "phase 1": "PHASE 1 - FRONT END", "parking lot": "PARKING LOT"}

var keys: Array = []
var labels := {}
var viewer: Node3D
var t := 0.0
var playing := false
var _said := {}


static func w(p: Array) -> Vector3:
	return Vector3(float(p[0]), float(p[2]), -float(p[1]))


func setup(d: Dictionary, who: Node3D) -> void:
	keys = d["keys"]
	viewer = who
	for name in d["labels"].keys():
		var l := Label3D.new()
		l.text = str(NAMES.get(name, name)).to_upper()
		l.font = FONT
		l.font_size = 96
		l.pixel_size = 0.1
		l.outline_size = 24
		l.outline_modulate = Color(0.07, 0.1, 0.33)
		l.modulate = Color(1, 0.9, 0.35, 0)
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l.no_depth_test = true
		l.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
		l.position = w(d["labels"][name])
		l.visible = false
		add_child(l)
		labels[name] = l


func length() -> float:
	return float(keys[-1]["t"]) if not keys.is_empty() else 0.0


func start() -> void:
	t = 0.0
	_said = {}
	playing = true


func finish() -> void:
	if not playing:
		return
	playing = false
	t = length()
	_place(t)
	for l in labels.values():
		l.visible = false
	done.emit()


func _segment(at: float) -> int:
	for i in keys.size() - 1:
		if at <= float(keys[i + 1]["t"]):
			return i
	return keys.size() - 2


func point(at: float) -> Vector3:
	var i := _segment(at)
	var p0 := w(keys[maxi(0, i - 1)]["at"])
	var p1 := w(keys[i]["at"])
	var p2 := w(keys[i + 1]["at"])
	var p3 := w(keys[mini(keys.size() - 1, i + 2)]["at"])
	var u := clampf((at - float(keys[i]["t"])) / (float(keys[i + 1]["t"]) - float(keys[i]["t"])), 0.0, 1.0)
	return 0.5 * ((2.0 * p1) + (-p0 + p2) * u + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * u * u
			+ (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * u * u * u)


func _place(at: float) -> void:
	var i := _segment(at)
	var u := clampf((at - float(keys[i]["t"])) / (float(keys[i + 1]["t"]) - float(keys[i]["t"])), 0.0, 1.0)
	var look := w(keys[i]["look"]).lerp(w(keys[i + 1]["look"]), smoothstep(0.0, 1.0, u))
	var p := point(at)
	viewer.global_position = p
	var d := look - p
	viewer.yaw = atan2(-d.x, -d.z)
	viewer.pitch = atan2(d.y, Vector2(d.x, d.z).length())


func _process(dt: float) -> void:
	if not playing:
		return
	t += dt
	if t >= length():
		finish()
		return
	_place(t)
	for k in keys:
		if float(k["t"]) <= t and not _said.has(float(k["t"])):
			_said[float(k["t"])] = true
			if k.has("say"):
				line.emit(str(k["say"]))
			if k.has("label") and labels.has(k["label"]):
				labels[k["label"]].visible = true
	for l in labels.values():
		if l.visible:
			l.modulate.a = minf(1.0, l.modulate.a + dt * 2.0)
