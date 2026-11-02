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
var speed := 1.4              # metres a second: an ordinary walk (the recorded tour sets it faster)
var _v := 0.0                 # the speed it is walking at now: it eases in and out of every stop
const ACCEL := 1.6            # metres a second, each second, speeding up or slowing down
const TURN := 3.2             # radians a second it can turn while walking: corners become arcs
const CLIP_SPEED := 0.94      # metres a second the walk clip covers at its own rate: its planted foot's speed, measured in
                              # Blender (0.92 to 0.97 m/s), so the clip runs at speed / 0.94 and the feet do not slide
const VIA_RADIUS := 0.7       # how close to a corner or door it gets before heading for the next point
var line_of: Callable         # stop -> its line, built from the live run when the guide arrives
var talk_scale := 1.0         # shorter pauses for the recorded tour
var hold := 0.0               # extra seconds at the next stop (a question asked there)
const LIFT_SPEED := 1.0       # metres a second, the lift's ride (assumed)
var viewer: Node3D            # the visitor, whom the guide turns to at a stop marked face_viewer
var shower_box: Array = []    # the air shower's box [x0, y0, z0, x1, y1, z1], plan metres: he ducks inside it
var _ducking := false
var _bonk_t := 0.0
const BONK_LINE := "Ow! Somebody log that defect: one cracked CEO. There goes the yield."


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
				anim.play(a, 0.3)
			# the clip's rate follows the walking speed every frame, so the planted foot keeps pace with the ground
			anim.speed_scale = rate
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


func _step_on() -> void:
	i += 1
	if i >= stops.size():
		mode = "idle"
		_play("Idle_Loop")
		tour_done.emit()


func _model() -> Node3D:
	return get_node_or_null("model") as Node3D


func _in_shower() -> bool:
	if shower_box.is_empty():
		return false
	var x := global_position.x
	var y := -global_position.z
	return x > float(shower_box[0]) - 0.45 and x < float(shower_box[3]) + 0.35 and y > float(shower_box[1]) and y < float(shower_box[4])


func _bonk() -> void:
	# walks into the air shower's frame head first: BONK, a line, then he ducks through
	mode = "bonk"
	_bonk_t = 0.0
	_v = 0.0
	_play("Idle_Loop")
	$bonk.visible = true
	said.emit(BONK_LINE)


func skip() -> void:
	# the visitor pressed on: end this line now
	if mode == "talk":
		talk_left = 0.0


var trace := false              # print the walk each half second (for checking the feet keep up)
var _tr := 0.0
var _tr_at := Vector3.ZERO


func _process(dt: float) -> void:
	if trace:
		_tr += dt
		if _tr >= 0.5:
			var moved := Vector2(global_position.x - _tr_at.x, global_position.z - _tr_at.z).length() / _tr
			print("walk mode=%s v=%.2f moved=%.2f clip=%s rate=%.2f playing=%s" % [mode, _v, moved,
					anim.current_animation if anim else "-", anim.speed_scale if anim else 0.0, anim.is_playing() if anim else false])
			_tr = 0.0
			_tr_at = global_position
	var mdl := _model()
	if mdl and mode != "bonk":
		# ducking is a cartoon squash (2.3 m down to 2.1 m, under the shower's 2.2 m ceiling) with a slight lean, so his
		# head stays inside the booth; a full lean from the feet swung it out through the side
		var in_booth := _ducking and _in_shower()
		var lean := 0.14 if in_booth else 0.0
		var squash := 0.9 if in_booth else 1.0
		mdl.rotation.x = lerpf(mdl.rotation.x, lean, clampf(dt * 6.0, 0.0, 1.0))
		mdl.scale = mdl.scale.lerp(Vector3(1.04 if in_booth else 1.0, squash, 1.04 if in_booth else 1.0), clampf(dt * 6.0, 0.0, 1.0))
		if _ducking and not _in_shower() and global_position.x > shower_box[3] + 0.3:
			_ducking = false
	if mode == "walk" and i < stops.size():
		var s: Dictionary = stops[i]
		var to: Vector3 = s["at"]
		if s.get("teleport", false):
			global_position = to
		var d := to - global_position
		d.y = 0.0
		if s.get("ride", false):
			# up or down in the lift, standing still
			var dy := to.y - global_position.y
			_v = 0.0
			_play("Idle_Loop")
			if absf(dy) < 0.02:
				global_position = to
				arrived.emit(s)
				_step_on()
			else:
				global_position.y += signf(dy) * minf(LIFT_SPEED * dt, absf(dy))
			return
		if s.get("teleport", false):
			global_position = to
			d = Vector3.ZERO
		var dist := d.length()
		var via: bool = s.get("via", false)
		if dist < (VIA_RADIUS if via else 0.06) or (not via and dist < 0.3 and _v < 0.15):
			if not via:
				global_position = Vector3(to.x, to.y, to.z)
				_v = 0.0
			arrived.emit(s)
			if via and s.get("bump", false):
				_bonk()          # too tall for the air shower's frame
			elif via:
				_step_on()       # carry on through the corner without stopping
			else:
				say(line_of.call(s) if line_of.is_valid() else str(s.get("say", "")), str(s.get("label", "")))
			return
		# head for the point at a limited turn rate; slow down for sharp turns and before a stop
		var want_yaw := atan2(d.x, d.z)
		var off := absf(angle_difference(rotation.y, want_yaw))
		rotation.y = rotate_toward(rotation.y, want_yaw, TURN * dt * (1.6 if _v < 0.4 else 1.0))
		var target_v := speed * clampf(1.0 - (off - 0.35) / 1.2, 0.0, 1.0)
		if not via:
			target_v = minf(target_v, sqrt(2.0 * ACCEL * maxf(dist - 0.05, 0.0)))
		_v = move_toward(_v, target_v, ACCEL * dt)
		var step := Vector3(sin(rotation.y), 0.0, cos(rotation.y)) * minf(_v * dt, dist)
		if off > 1.2:
			step = Vector3.ZERO      # turn on the spot first
		global_position += step
		global_position.y = to.y
		if _v > 0.12:
			_play("Walk_Formal_Loop", _v / CLIP_SPEED)
		else:
			_play("Idle_Loop")
	elif mode == "bonk":
		_bonk_t += dt
		var m := _model()
		if m:
			# the head snaps back and settles
			m.rotation.x = -0.35 * exp(-_bonk_t * 4.0) * sin(_bonk_t * 14.0)
		if _bonk_t > 2.8:
			if m:
				m.rotation.x = 0.0
			$bonk.visible = false
			_ducking = true
			_step_on()
			mode = "walk" if i < stops.size() else mode
	elif mode == "talk":
		if i < stops.size() and stops[i].has("face"):
			rotation.y = lerp_angle(rotation.y, float(stops[i]["face"]), clampf(dt * 3.0, 0.0, 1.0))
		if viewer and i < stops.size() and stops[i].get("face_viewer", false):
			var to_v := viewer.global_position - global_position
			rotation.y = lerp_angle(rotation.y, atan2(to_v.x, to_v.z), clampf(dt * 4.0, 0.0, 1.0))
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
