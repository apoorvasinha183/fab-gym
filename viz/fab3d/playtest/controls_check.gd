extends SceneTree
## Run against the real game, with no helper or paid services. Exit nonzero on a failed consequence.
## Godot --headless --path viz/fab3d --script res://playtest/controls_check.gd -- --playability-check OUT.json

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
	if not game.has_method("choose_view"):
		expect("first launch provides playable camera choices without a helper", false)
		finish()
		return
	var p: Node3D = game.player
	var menu: Node = game.play_menu
	expect("welcome opens before movement", menu.is_open() and paused)
	expect("welcome has a keyboard focus target", root.gui_get_focus_owner() is Button)
	menu.close()
	game.choose_view("tour")
	expect("tour starts without a live run", game.intro and game.drone.playing)
	game._free_walk()
	var here := p.global_position
	await create_timer(0.15).timeout
	expect("walking cancels the drone camera", not game.intro and not game.drone.playing and p.roaming)
	expect("cancelled drone cannot move the walker", p.global_position.distance_to(here) < 0.2)
	game.travel_to("Phase one")
	expect("travel leaves a standing free camera", p.roaming and not p.seated and p.follow == null)
	p.glide(p.global_position + Vector3(10, 0, 0), 0, 0, 0.2)
	game.travel_to("Bridge")
	here = p.global_position
	await create_timer(0.3).timeout
	expect("travel cancels an old cinematic tween", p.global_position.distance_to(here) < 0.2)
	p.autopilot = [{"at": p.global_position + Vector3(10, -1.65, 0)}]
	game.ui.ask_panel.show()
	game.ui.ask_box.grab_focus()
	here = p.global_position
	await create_timer(0.15).timeout
	expect("typing suspends autonomous camera movement", p.global_position.distance_to(here) < 0.01)
	game.ui.ask_box.release_focus()
	game.ui.ask_panel.hide()
	game.travel_to("Phase one")
	var old_yaw: float = p.yaw
	Input.action_press("look_right")
	await create_timer(0.15).timeout
	Input.action_release("look_right")
	expect("keyboard-only looking turns the view", absf(p.yaw - old_yaw) > 0.05)
	here = p.global_position
	Input.action_press("walk_forward")
	await create_timer(0.15).timeout
	Input.action_release("walk_forward")
	expect("mapped movement moves the visitor", p.global_position.distance_to(here) > 0.2)
	menu.open(false)
	here = p.global_position
	Input.action_press("walk_forward")
	await create_timer(0.15, true).timeout
	Input.action_release("walk_forward")
	expect("pause freezes the world", p.global_position.distance_to(here) < 0.01 and paused)
	menu.close()
	game.choose_view("fly")
	expect("flight is reachable from the menu", p.fly and p.roaming)
	game._free_walk()
	expect("Walk alone lands a flying visitor", not p.fly and p.roaming)
	game.choose_view("tour")
	game._rule_answer("show me the polishers")
	expect("asking for a place cancels the opening flight", not game.intro and not game.drone.playing)
	game.travel_to("Cinema")
	game.cinema.sit("R5C4")
	await process_frame
	expect("seated camera uses its own eye point", p.seated and p.global_position.distance_to(p.seat_eye) < 0.01)
	game.cinema.play()
	game.cinema.fullscreen(true)
	expect("movie locks world input", p.input_locked and root.disable_3d)
	game._tour_finished()
	expect("tour completion cannot interrupt a seated film", p.seated and game.cinema.full.visible and p.input_locked)
	game.travel_to("Parking lot")
	expect("travel exits movie and restores the world", not p.seated and not p.input_locked and not root.disable_3d)
	game.choose_view("tour")
	game.drone.finish()
	var before: int = game.guide.i
	game._on_run({"run": "late"})
	expect("late live connection cannot restart the camera", not game.intro and game.guide.i == before)
	game._free_walk()
	game._lou_waiting = true
	game.travel_to("Bridge")
	here = p.global_position
	game._on_lou({"ok": true, "walk_to": "Litho", "say": "late answer"})
	expect("late guide answer cannot seize the new camera", p.follow == null and p.global_position == here)
	game.ui.ask_panel.show()
	game.ui.ask_box.grab_focus()
	var fly_before: bool = p.fly
	var key := InputEventKey.new()
	key.keycode = KEY_F
	key.pressed = true
	p._unhandled_input(key)
	expect("typing F cannot toggle flight", p.fly == fly_before)
	game.ui.ask_box.release_focus()
	game.ui.ask_panel.hide()
	# Every tour device is optional: empty bays must remain inspectable without indexing a missing tool.
	var valid := true
	for stop in game._tour():
		if stop.get("kind") == "area":
			var device: Dictionary = stop.get("device", {})
			valid = valid and (device.is_empty() or int(device["tool"]) < game.campus.data["tools"].size())
	expect("empty bays have a safe tour view", valid)
	for place in ["Parking lot", "Phase one", "Bridge", "Phase two", "Cinema"]:
		game.travel_to(place)
		await physics_frame
		await process_frame
		var probe := SphereShape3D.new()
		probe.radius = 0.18
		var q := PhysicsShapeQueryParameters3D.new()
		q.shape = probe
		q.transform.origin = p.global_position
		var hits := p.get_world_3d().direct_space_state.intersect_shape(q)
		expect("safe arrival: " + place, hits.is_empty() and p.global_position.is_finite())
	game.live._use_demo()
	expect("offline play has recorded simulation data", game.live.offline and game.live.demo.get("frames", []).size() > 0)
	finish()


func finish() -> void:
	var args := OS.get_cmdline_user_args()
	var at := args.find("--playability-check")
	if at >= 0 and at + 1 < args.size():
		var f := FileAccess.open(args[at + 1], FileAccess.WRITE)
		f.store_string(JSON.stringify(checks, "  "))
	var failed := checks.values().count(false)
	print("Playability: %d passed, %d failed" % [checks.size() - failed, failed])
	quit(1 if failed else 0)
