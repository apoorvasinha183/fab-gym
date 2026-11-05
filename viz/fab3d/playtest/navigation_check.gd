extends SceneTree
## Real scene regression: input ownership, trackpads and map position/orientation.
## Godot --headless --path viz/fab3d --script res://playtest/navigation_check.gd -- --playability-check OUT.json

var checks := {}
var game: Node

func _initialize() -> void:
	_run.call_deferred()

func expect(name: String, passed: bool) -> void:
	checks[name] = passed
	print("%s: %s" % ["PASS" if passed else "FAIL", name])

func _run() -> void:
	game = load("res://main.tscn").instantiate()
	root.add_child(game)
	await process_frame
	await process_frame
	var p: Node3D = game.player
	var map: CanvasLayer = game.minimap
	expect("map stays out of welcome menu", not map.panel.visible)
	game.play_menu.close()
	game.choose_view("walk")
	await process_frame
	await process_frame
	map._process(0.1)
	expect("map appears when exploring", map.panel.visible)
	var pan := InputEventPanGesture.new()
	pan.delta = Vector2(12, 8)
	var before := Vector2(p.yaw, p.pitch)
	p._unhandled_input(pan)
	expect("two-finger gesture turns both camera axes without capture", p.yaw > before.x and p.pitch > before.y and Input.mouse_mode == Input.MOUSE_MODE_VISIBLE)
	before = Vector2(p.yaw, p.pitch)
	p.invert_look = true
	p._unhandled_input(pan)
	expect("trackpad honours vertical inversion", p.pitch < before.y and p.yaw > before.x)
	p.invert_look = false
	p.look_sensitivity = 0.5
	before.x = p.yaw
	p._unhandled_input(pan)
	expect("trackpad honours look sensitivity", is_equal_approx(p.yaw - before.x, 0.03))
	p.look_sensitivity = 1.0
	p.reverse_trackpad = true
	before = Vector2(p.yaw, p.pitch)
	p._unhandled_input(pan)
	expect("trackpad direction preference reverses both axes", p.yaw < before.x and p.pitch < before.y)
	p.reverse_trackpad = false
	var wheel := InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
	wheel.pressed = true
	wheel.factor = 0.25
	before.y = p.pitch
	p._unhandled_input(wheel)
	expect("precise wheel keeps fractional movement", is_equal_approx(p.pitch - before.y, 0.02))
	wheel.button_index = MOUSE_BUTTON_WHEEL_RIGHT
	before.x = p.yaw
	p._unhandled_input(wheel)
	expect("horizontal scroll turns camera", absf(before.x - p.yaw) > 0.01)
	wheel.ctrl_pressed = true
	before = Vector2(p.yaw, p.pitch)
	p._unhandled_input(wheel)
	expect("pinch or browser zoom cannot steer camera", Vector2(p.yaw, p.pitch) == before)
	game.ui.ask_panel.show()
	game.ui.ask_box.grab_focus()
	p._unhandled_input(pan)
	expect("typing does not steer camera", Vector2(p.yaw, p.pitch) == before)
	game.ui.ask_box.release_focus()
	game.ui.ask_panel.hide()
	p.roaming = false
	p._unhandled_input(pan)
	expect("trackpad cannot fight the guided camera", Vector2(p.yaw, p.pitch) == before)
	p.roaming = true
	p.input_locked = true
	p._unhandled_input(pan)
	expect("locked film camera ignores gestures", Vector2(p.yaw, p.pitch) == before)
	p.input_locked = false
	game.play_menu.open()
	p._unhandled_input(pan)
	expect("paused camera ignores gestures", Vector2(p.yaw, p.pitch) == before)
	game.play_menu.close()
	# Dispatch through the viewport to prove the UI, not only the player guard, owns map scrolling.
	pan.position = map.drawing.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = pan.position
	root.push_input(motion, true)
	root.push_input(pan, true)
	expect("scrolling over map is consumed before reaching camera", Vector2(p.yaw, p.pitch) == before)
	pan.position = Vector2(960, 400)
	motion.position = pan.position
	root.push_input(motion, true)
	root.push_input(pan, true)
	expect("gesture over the world reaches camera", Vector2(p.yaw, p.pitch) != before)
	if DisplayServer.get_name() != "headless":
		p.toggle_mouse_look()
		expect("one-finger mode captures the pointer", Input.mouse_mode == Input.MOUSE_MODE_CAPTURED)
		before = Vector2(p.yaw, p.pitch)
		p._prime_look = true
		motion.relative = Vector2(800, 600)
		p._unhandled_input(motion)
		expect("starting look discards stale cursor movement", Vector2(p.yaw, p.pitch) == before)
		motion.relative = Vector2(20, 0)
		p._unhandled_input(motion)
		expect("one-finger motion steers without a held button", is_equal_approx(before.x - p.yaw, 0.05))
		var release := InputEventMouseButton.new()
		release.button_index = MOUSE_BUTTON_RIGHT
		p._input(release)
		expect("right release cannot cancel latched look", Input.mouse_mode == Input.MOUSE_MODE_CAPTURED)
		game.play_menu.open()
		expect("pause releases pointer and clears latch", Input.mouse_mode == Input.MOUSE_MODE_VISIBLE and not p._look_latched)
		game.play_menu.close()
	for spec in [[0.0, Vector2.UP], [-PI / 2, Vector2.RIGHT], [PI, Vector2.DOWN], [PI / 2, Vector2.LEFT]]:
		p.yaw = spec[0]
		expect("map heading at %.2f radians" % spec[0], map.heading_vector().distance_to(spec[1]) < 0.001)
	var arrivals := true
	for name in ["Parking lot", "Phase one", "Bridge", "Phase two", "Cinema"]:
		game.travel_to(name)
		map.update_transform()
		arrivals = arrivals and map.plan_to_map(map.player_plan()).distance_to(map.drawing.size * 0.5) < 0.001
	expect("nearby map keeps player centred at all destinations", arrivals)
	map.toggle_overview()
	var inside := true
	for f in game.campus.data["fabs"]:
		for at in [Vector2(f[0], f[2]), Vector2(f[1], f[3])]:
			inside = inside and Rect2(Vector2.ZERO, map.drawing.size).has_point(map.plan_to_map(at))
	for at in map.landmarks().values():
		inside = inside and Rect2(Vector2.ZERO, map.drawing.size).has_point(map.plan_to_map(at))
	expect("campus overview contains buildings and destinations", inside)
	game.choose_view("fly")
	p.global_position = Vector3(-400, 60, 300)
	map.update_transform()
	expect("overview retains a visitor flying outside campus", Rect2(Vector2.ZERO, map.drawing.size).has_point(map.plan_to_map(map.player_plan())))
	map.places.selected = 4
	map.places.get_parent().get_child(1).pressed.emit()
	expect("map Go reaches selected safe place and leaves flight", not p.fly and p.global_position.x == 58 and p.global_position.z == 104)
	game.cinema.sit("R5C4")
	p.toggle_mouse_look()
	game.cinema.fullscreen(true)
	expect("film clears one-finger look before returning to the hall", not p._look_latched)
	map._process(0.1)
	expect("full-screen film hides the map", not map.panel.visible)
	game.travel_to("Phase one")
	map.toggle_overview()
	var args := OS.get_cmdline_user_args()
	if "--stills" in args and DisplayServer.get_name() != "headless":
		var out := args[args.find("--stills") + 1]
		DirAccess.make_dir_recursive_absolute(out)
		for shape in [Vector2i(1280, 720), Vector2i(800, 1000), Vector2i(1920, 720)]:
			root.size = shape
			await create_timer(0.3).timeout
			map._process(0.1)
			await RenderingServer.frame_post_draw
			expect("map fits viewport %s" % str(shape), root.get_visible_rect().encloses(map.panel.get_global_rect()))
			root.get_texture().get_image().save_png(out.path_join("nearby-%dx%d.png" % [shape.x, shape.y]))
		root.size = Vector2i(1280, 720)
		map.toggle_overview()
		await create_timer(0.2).timeout
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(out.path_join("campus.png"))
	var at := args.find("--playability-check")
	if at >= 0 and at + 1 < args.size():
		FileAccess.open(args[at + 1], FileAccess.WRITE).store_string(JSON.stringify(checks, "  "))
	var failed := checks.values().count(false)
	print("Navigation: %d passed, %d failed" % [checks.size() - failed, failed])
	quit(1 if failed else 0)
