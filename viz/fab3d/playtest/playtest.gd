extends Node
## The playtest (viz/playtest/README.md): plays the whole demo as a first-time visitor would, with scripted key presses,
## and logs every frame: frame time, where the camera is and whether it is inside something solid or under a floor,
## whether Lou is on screen, inside something, stuck or sliding, what the screen windows show and whether they overlap,
## and the doors near Lou. Stills are saved small. It fixes nothing; viz/playtest/analyse.py turns the log into faults.
## From the SMT2020 testbed; not a real fab.
##
##   Godot --path viz/fab3d res://playtest/playtest.tscn -- --playtest OUT_DIR [--no-intro] [--cinema]

var out := ""
var main: Node
var guide: Node3D
var player: Node3D
var ui: CanvasLayer
var cinema: Node3D
var cam: Camera3D
var t := 0.0
var _row_t := 0.0
var _shot_t := 0.0
var _shot_n := 0
var _log: FileAccess
var _frames: FileAccess
var _shots_due: Array = []         # [time, tag]
var _steps: Array = []             # scripted visitor actions: [time, callable, name]
var _held := {}                    # keys held down by the script
var _walk_to = null                # Vector3 target the scripted visitor walks to
var _walk_since := 0.0
var _probe := SphereShape3D.new()
var _lou_body := CapsuleShape3D.new()
var _stage := "start"
var _cinema_done := false
var _litho_done := false
var _areas_seen := 0
const ROW_EVERY := 0.2
const SHOT_EVERY := 3.0
const CAP_SECONDS := 2700.0


func _ready() -> void:
	process_priority = 1000            # after the game has moved everything this frame
	var args := OS.get_cmdline_user_args()
	if "--playtest" in args:
		out = args[args.find("--playtest") + 1]
	DirAccess.make_dir_recursive_absolute(out + "/shots")
	_log = FileAccess.open(out + "/log.jsonl", FileAccess.WRITE)
	_frames = FileAccess.open(out + "/frames.csv", FileAccess.WRITE)
	_frames.store_line("t,ms")
	_probe.radius = 0.12
	_lou_body.radius = 0.22
	_lou_body.height = 1.1
	main = load("res://main.tscn").instantiate()
	add_child(main)
	guide = main.guide
	player = main.player
	ui = main.ui
	cinema = main.cinema
	cam = player.camera
	guide.said.connect(func(text: String) -> void: _event("said", {"text": text, "chars": text.length()}))
	guide.arrived.connect(_on_arrived)
	guide.tour_done.connect(func() -> void: _event("tour_done", {}))
	main.drone.done.connect(func() -> void: _event("intro_done", {}))
	cinema.prompt.connect(func(text: String) -> void: _event("prompt", {"text": text}))
	_event("start", {"args": Array(args), "window": [get_viewport().get_visible_rect().size.x, get_viewport().get_visible_rect().size.y]})


# ------------------------------------------------------------------ the scripted visitor

func _on_arrived(s: Dictionary) -> void:
	var kind := str(s.get("kind", ""))
	if s.get("via", false):
		return
	_event("arrived", {"kind": kind, "label": str(s.get("label", "")), "area": str(s.get("area", "")),
			"at": [s["at"].x, -s["at"].z, s["at"].y]})
	_shots_due.append([t + 1.5, "arrive-" + kind + "-" + str(s.get("area", ""))])
	_shots_due.append([t + 6.0, "talk-" + kind + "-" + str(s.get("area", ""))])
	if kind == "area":
		_areas_seen += 1
		if _areas_seen == 3:
			# a visitor who reads fast presses Space twice: finish the line, then move on
			_at(t + 2.0, func() -> void: _key(KEY_SPACE), "space: finish the line")
			_at(t + 2.6, func() -> void: _key(KEY_SPACE), "space: next")
		if str(s.get("area", "")) == "Litho" and not _litho_done:
			_litho_done = true
			_at(t + 4.0, _click_a_tool, "click the nearest tool for its card")
			_at(t + 8.0, func() -> void: _key(KEY_ESCAPE), "esc: close the card")
			_at(t + 9.0, func() -> void: _ask("why is this queue long?"), "ask: why is this queue long?")
			_at(t + 12.0, func() -> void: _ask("what is lithography?"), "ask: what is lithography?")
			_at(t + 15.0, func() -> void: _press_ui("root/menu/list/speed"), "menu: speed")
			_at(t + 25.0, func() -> void: _press_ui("root/menu/list/speed"), "menu: speed")
			_at(t + 26.0, func() -> void: _press_ui("root/menu/list/speed"), "menu: speed back to real time")
	if kind == "cinema" and not _cinema_done:
		_cinema_done = true
		_stage = "cinema"
		var seat := _free_seat_near(Vector3(54.5, 0.0, 116.0))
		_at(t + 5.0, func() -> void: _walk(seat), "walk to a free seat")
		_at(t + 25.0, func() -> void: _key(KEY_E), "e: sit down")
		_at(t + 28.0, func() -> void: _key(KEY_ENTER), "enter: play the film full screen")
		_at(t + 36.0, func() -> void: _key(KEY_SPACE), "space: pause")
		_at(t + 39.0, func() -> void: _key(KEY_SPACE), "space: resume")
		_at(t + 44.0, func() -> void: _key(KEY_ESCAPE), "esc: back to the hall")
		_at(t + 48.0, func() -> void: _key(KEY_E), "e: stand up")
		_at(t + 51.0, func() -> void: _press_ui("root/menu/list/free"), "menu: walk alone")
		_at(t + 52.0, func() -> void: _walk(Vector3(44.0, 0.0, 116.0)), "walk towards the screen")
		_at(t + 62.0, func() -> void: _walk(Vector3(58.15 + 3.0, 0.0, 118.7)), "walk out by the rear exit")
		_at(t + 74.0, func() -> void: _key(KEY_F), "f: fly")
		_at(t + 74.5, func() -> void: _hold(KEY_E, 2.0), "hold e: up")
		_at(t + 77.0, func() -> void: _hold(KEY_W, 3.0), "hold w: forward while flying")
		_at(t + 80.5, func() -> void: _key(KEY_F), "f: land")
		_at(t + 82.0, func() -> void: _ask("show me the polishers"), "ask: show me the polishers")
		_at(t + 100.0, func() -> void: _finish("script done"), "end")


func _at(when: float, what: Callable, name: String) -> void:
	_steps.append([when, what, name])
	_steps.sort_custom(func(a, b) -> bool: return a[0] < b[0])


func _key(code: int, down := true) -> void:
	var e := InputEventKey.new()
	e.keycode = code
	e.physical_keycode = code
	e.pressed = down
	Input.parse_input_event(e)
	if down:
		var up := InputEventKey.new()
		up.keycode = code
		up.physical_keycode = code
		up.pressed = false
		get_tree().create_timer(0.08).timeout.connect(func() -> void: Input.parse_input_event(up))


func _hold(code: int, seconds: float) -> void:
	var e := InputEventKey.new()
	e.keycode = code
	e.physical_keycode = code
	e.pressed = true
	Input.parse_input_event(e)
	_held[code] = t + seconds


func _ask(q: String) -> void:
	ui.ask_panel.show()
	ui.ask_box.text = q
	ui.ask_box.text_submitted.emit(q)


func _press_ui(path: String) -> void:
	var b := ui.get_node_or_null(path) as Button
	if b:
		b.pressed.emit()
	else:
		_event("fault_harness", {"why": "no button " + path})


func _click_a_tool() -> void:
	# the nearest drawn tool in view, clicked at its centre on screen
	var best := -1
	var bd := 1e9
	for i in main.campus.tool_nodes.keys():
		var tt: Array = main.campus.data["tools"][i]
		var c := Vector3((float(tt[4]) + float(tt[5])) / 2.0, 8.6, -(float(tt[6]) + float(tt[7])) / 2.0)
		if not cam.is_position_in_frustum(c):
			continue
		var d := c.distance_to(cam.global_position)
		if d < bd:
			bd = d
			best = i
	if best < 0:
		_event("fault_harness", {"why": "no tool in view to click"})
		return
	var tt: Array = main.campus.data["tools"][best]
	var c := Vector3((float(tt[4]) + float(tt[5])) / 2.0, 8.6, -(float(tt[6]) + float(tt[7])) / 2.0)
	var at := cam.unproject_position(c)
	var e := InputEventMouseButton.new()
	e.button_index = MOUSE_BUTTON_LEFT
	e.pressed = true
	e.position = at
	e.global_position = at
	Input.parse_input_event(e)
	_event("clicked", {"tool": str(tt[0]), "screen": [at.x, at.y]})
	_shots_due.append([t + 1.0, "tool-card"])


func _free_seat_near(p: Vector3) -> Vector3:
	var best := Vector3.ZERO
	var bd := 1e9
	for id in cinema.seats:
		if cinema.taken.has(id):
			continue
		var s: Array = cinema.seats[id]
		var d := Vector2(s[0] - p.x, -s[1] - p.z).length()
		if d < bd:
			bd = d
			best = Vector3(s[0] - 0.6, 0.0, -s[1])
	return best


func _walk(target: Vector3) -> void:
	_walk_to = target
	_walk_since = t
	_event("walk", {"to": [target.x, -target.z]})


func _steer(dt: float) -> void:
	# the scripted visitor turns towards the target and holds W, as a person would, until there or stuck
	if _walk_to == null:
		return
	var d: Vector3 = _walk_to - player.global_position
	d.y = 0.0
	if d.length() < 0.25 or t - _walk_since > 10.0:
		_event("walk_end", {"left_m": d.length(), "seconds": t - _walk_since, "at": [player.global_position.x, -player.global_position.z]})
		_walk_to = null
		_key(KEY_W, false)
		return
	player.yaw = lerp_angle(player.yaw, atan2(-d.x, -d.z), clampf(dt * 6.0, 0.0, 1.0))
	if not Input.is_key_pressed(KEY_W):
		var e := InputEventKey.new()
		e.keycode = KEY_W
		e.physical_keycode = KEY_W
		e.pressed = true
		Input.parse_input_event(e)


func _finish(why: String) -> void:
	_event("end", {"why": why})
	_log.flush()
	_frames.flush()
	get_tree().quit()


# ------------------------------------------------------------------ what is logged

func _event(kind: String, data: Dictionary) -> void:
	data["ev"] = kind
	data["t"] = snappedf(t, 0.01)
	_log.store_line(JSON.stringify(data))


func _solid_at(p: Vector3, shape: Shape3D) -> String:
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape
	q.transform = Transform3D(Basis(), p)
	var hits := player.get_world_3d().direct_space_state.intersect_shape(q, 1)
	if hits.is_empty():
		return ""
	var o = hits[0].get("collider")
	return str(o.get_parent().name) if o and o.get_parent() else "?"


func _rect(c: Control) -> Array:
	if not c or not c.is_visible_in_tree():
		return []
	var r := c.get_global_rect()
	return [r.position.x, r.position.y, r.size.x, r.size.y]


func _row() -> void:
	var cp := cam.global_position
	var floor_y: float = player.floor_at(cp.x, -cp.z)
	var head := guide.global_position + Vector3(0, 1.7, 0)
	var lou_on := cam.is_position_in_frustum(head)
	var lou_hidden := ""
	if lou_on:
		var ray := PhysicsRayQueryParameters3D.create(cp, head)
		var hit := player.get_world_3d().direct_space_state.intersect_ray(ray)
		if not hit.is_empty():
			var o = hit.get("collider")
			lou_hidden = str(o.get_parent().name) if o and o.get_parent() else "?"
	var lou_feet := guide.global_position.y
	var stops: Array = guide.stops
	var si: int = guide.i
	var stop: Dictionary = stops[si] if si < stops.size() else {}
	var anim: AnimationPlayer = guide.anim
	var line: RichTextLabel = ui.line_label
	var row := {"ev": "row", "t": snappedf(t, 0.01),
		"cam": [snappedf(cp.x, 0.01), snappedf(-cp.z, 0.01), snappedf(cp.y, 0.01)], "yaw": snappedf(player.yaw, 0.01),
		"pitch": snappedf(player.pitch, 0.01), "cam_floor": snappedf(floor_y, 0.01),
		"cam_in_solid": _solid_at(cp, _probe),
		"lou": [snappedf(guide.global_position.x, 0.01), snappedf(-guide.global_position.z, 0.01), snappedf(lou_feet, 0.01)],
		"lou_mode": str(guide.mode), "lou_v": snappedf(float(guide.get("_v")), 0.01),
		"clip": anim.current_animation if anim else "", "rate": snappedf(anim.speed_scale, 0.01) if anim else 0.0,
		"stop_i": si, "stop_kind": str(stop.get("kind", "")), "stop_via": stop.get("via", false),
		"stop_area": str(stop.get("area", "")),
		"lou_in_frustum": lou_on, "lou_hidden_by": lou_hidden, "lou_dist": snappedf(cp.distance_to(head), 0.01),
		"lou_in_solid": _solid_at(guide.global_position + Vector3(0, 0.5 + 0.55, 0), _lou_body),
		"follow": player.follow != null, "roaming": player.roaming, "seated": player.seated, "fly": player.fly,
		"talk_visible": ui.get_node("root/talk").visible, "talk_alpha": snappedf(ui.get_node("root/talk").modulate.a, 0.01),
		"line_chars": line.get_total_character_count(), "line_shown": snappedf(line.visible_ratio, 0.01),
		"line_overflow": line.get_content_height() > line.size.y + 1.0,
		"stop_label": ui.stop_label.text, "prompt": ui.prompt_label.text if ui.prompt_panel.visible else "",
		"card": ui.card.visible, "ask": ui.ask_panel.visible, "intro": main.intro, "touring": main.touring,
		"film_full": cinema.full.visible, "film_started": cinema.started, "film_paused": cinema.video.paused,
		"film_pos": snappedf(cinema.video.stream_position, 0.01) if cinema.video.stream else -1.0,
		"rects": {"talk": _rect(ui.get_node("root/talk")), "face": _rect(ui.get_node("root/face")),
			"menu": _rect(ui.get_node("root/menu")), "status": _rect(ui.get_node("root/status")),
			"ask": _rect(ui.ask_panel), "card": _rect(ui.card), "prompt": _rect(ui.prompt_panel),
			"hint": _rect(ui.hint)},
		"clock": ui.clock_label.text, "fps": Engine.get_frames_per_second()}
	var doors := []
	for dr in cinema.doors:
		var c: Vector3 = dr[2]
		var dl := Vector2(guide.global_position.x - c.x, guide.global_position.z - c.z).length()
		var dp := Vector2(cp.x - c.x, cp.z - c.z).length()
		if dl < 1.2 or dp < 1.2:
			doors.append({"door": str(dr[4].get("name", "entrance")), "open": snappedf(float(dr[3]), 0.01),
				"lou_m": snappedf(dl, 0.01), "cam_m": snappedf(dp, 0.01)})
	row["doors"] = doors
	_log.store_line(JSON.stringify(row))


func _shot(tag: String) -> void:
	var img := get_viewport().get_texture().get_image()
	if img == null:
		return
	img.resize(960, 540, Image.INTERPOLATE_BILINEAR)
	var path := "%s/shots/%04d-%06.1f-%s.jpg" % [out, _shot_n, t, tag.replace("/", "_")]
	img.save_jpg(path, 0.82)
	_shot_n += 1


func _process(dt: float) -> void:
	t += dt
	_frames.store_line("%.3f,%.2f" % [t, dt * 1000.0])
	_steer(dt)
	for code in _held.keys():
		if t >= float(_held[code]):
			_key(code, false)
			_held.erase(code)
	while not _steps.is_empty() and t >= float(_steps[0][0]):
		var s: Array = _steps.pop_front()
		_event("step", {"name": s[2]})
		(s[1] as Callable).call()
		_shots_due.append([t + 1.2, "step-" + str(s[2]).split(":")[0].replace(" ", "_")])
	_row_t += dt
	if _row_t >= ROW_EVERY:
		_row_t = 0.0
		_row()
	_shot_t += dt
	if _shot_t >= SHOT_EVERY:
		_shot_t = 0.0
		_shot("every")
	_shots_due.sort_custom(func(a, b) -> bool: return a[0] < b[0])
	while not _shots_due.is_empty() and t >= float(_shots_due[0][0]):
		var sd: Array = _shots_due.pop_front()
		_shot(str(sd[1]))
	if t > CAP_SECONDS:
		_finish("time cap")
