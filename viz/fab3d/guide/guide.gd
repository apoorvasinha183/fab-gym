extends Node3D
## The robot CEO who gives the tour (docs/FAB-3D.md): it walks from stop to stop with the CC0 formal walk, and at each
## stop says its line (the bubble above its head and the panel) with the CC0 talking clip. "Show me" sends it to a place;
## it never makes up a number: every number it says comes from the live run. From the SMT2020 testbed; not a real fab.

signal said(text: String)
signal arrived(stop: Dictionary)
signal tour_done

var anim: AnimationPlayer
var stops: Array = []
var i := 0
var mode := "idle"            # idle, walk, talk
var talk_left := 0.0
var speed := 3.2              # metres a second: faster than life, so the tour keeps moving
var line_of: Callable         # stop -> its line, built from the live run when the guide arrives
var talk_scale := 1.0         # shorter pauses for the recorded tour
var hold := 0.0               # extra seconds at the next stop (a question asked there)


func _ready() -> void:
	anim = _find_anim(self)
	_play("Idle_Loop")


func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var a := _find_anim(c)
		if a:
			return a
	return null


func _play(name: String, rate := 1.0) -> void:
	if not anim:
		return
	# Godot's importer drops "_Loop" from a clip's name and loops it itself
	var short := name.trim_suffix("_Loop")
	for a in anim.get_animation_list():
		if a == name or a == short or a.ends_with("/" + short):
			if anim.current_animation != a:
				anim.play(a, 0.25, rate)
			else:
				anim.speed_scale = 1.0
			return


func start(tour: Array) -> void:
	stops = tour
	i = 0
	mode = "walk" if not stops.is_empty() else "idle"


func go_to(stop: Dictionary) -> void:
	stops = [stop]
	i = 0
	mode = "walk"


func say(text: String, title := "") -> void:
	$bubble.text = title
	said.emit(text)
	mode = "talk"
	talk_left = clampf(text.length() / 15.0, 5.0, 14.0) * talk_scale + hold
	hold = 0.0
	_play("Idle_Talking_Loop")


func _process(dt: float) -> void:
	if mode == "walk" and i < stops.size():
		var s: Dictionary = stops[i]
		var to: Vector3 = s["at"]
		if s.get("teleport", false):
			global_position = to
		var d := to - global_position
		d.y = 0.0
		if d.length() < 0.3:
			global_position = to
			if s.has("face"):
				rotation.y = float(s["face"])
			arrived.emit(s)
			say(line_of.call(s) if line_of.is_valid() else str(s.get("say", "")), str(s.get("label", "")))
		else:
			var step := d.normalized() * minf(speed * dt, d.length())
			global_position += step
			global_position.y = to.y
			rotation.y = lerp_angle(rotation.y, atan2(d.x, d.z), clampf(dt * 6.0, 0.0, 1.0))
			_play("Walk_Formal_Loop", speed / 1.4)
	elif mode == "talk":
		talk_left -= dt
		if talk_left <= 0.0:
			i += 1
			if i >= stops.size():
				mode = "idle"
				$bubble.text = ""
				_play("Idle_Loop")
				tour_done.emit()
			else:
				mode = "walk"
