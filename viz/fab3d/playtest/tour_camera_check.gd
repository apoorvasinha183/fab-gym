extends SceneTree
## Replay the real guide route in fixed steps, checking the view while walking and at every stop.
## Godot --headless --path viz/fab3d --script res://playtest/tour_camera_check.gd -- --playability-check --tour-camera-check OUT.json

var game: Node
var samples := []
var stops := []
var elapsed := 0.0
var talk_time := 0.0
var last_stop := -1
var worst := 0.0
var out := ""
var stills := ""
var contacts := []
var stuck := false
var still_for := 0.0
var last_position := Vector3.ZERO


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	out = args[args.find("--tour-camera-check") + 1]
	if "--stills" in args:
		stills = args[args.find("--stills") + 1]
		DirAccess.make_dir_recursive_absolute(stills)
	game = load("res://main.tscn").instantiate()
	root.add_child(game)
	await process_frame
	game.play_menu.close()
	if not game.nav_ready:
		await game.nav_baked
	game.no_intro = true
	game.choose_view("tour")
	game.set_process(false)
	game.guide.set_process(false)
	game.player.set_process(false)
	game.entrance.set_process(false)
	var g: Node3D = game.guide
	var p: Node3D = game.player
	for tick in 90000:
		g._process(0.05)
		game.entrance._process(0.05)
		p._process(0.05)
		elapsed += 0.05
		if g.mode == "talk":
			talk_time += 0.05
		else:
			talk_time = 0.0
		if g.mode == "talk" and talk_time >= 3.0 and last_stop != g.i:
			last_stop = g.i
			var s: Dictionary = g.stops[g.i]
			var device: Dictionary = {} if s.get("face_viewer", false) else s.get("device", {})
			var target: Vector3 = device.get("target", g.global_position + Vector3(0, 1.6, 0))
			var row := measure(target)
			row["stop"] = game._stop_title(s)
			row["kind"] = s.kind
			row["subject_visible"] = (row.hit_body == "solid_tools" and row.hit_shape == int(device.tool)) if not device.is_empty() else row.hit_body == ""
			if device.is_empty():
				var side: Vector3 = (target - p.camera.global_position).cross(Vector3.UP).normalized() * 0.35
				row["subject_visible"] = row.subject_visible and measure(target + side).hit_body == "" and measure(target - side).hit_body == ""
			row["subject_visible"] = row.subject_visible and Vector2(p.position.x - g.position.x, p.position.z - g.position.z).length() >= 1.2
			stops.append(row)
			print("TOUR STOP ", JSON.stringify(row))
			if stills != "":
				game.campus.update_cells(true)
				await process_frame
				await process_frame
				RenderingServer.force_draw()
				var img := root.get_texture().get_image()
				img.resize(1280, 720)
				img.save_png(stills.path_join("%02d-%s.png" % [stops.size(), s.kind]))
		if tick % 10 == 0 and g.mode == "walk" and p.follow == g:
			var row := measure(g.global_position + Vector3(0, 1.6, 0))
			row["next"] = game._stop_title(g.stops[g.i])
			samples.append(row)
			worst = maxf(worst, float(row.angle))
			var body := CapsuleShape3D.new()
			body.radius = 0.22
			body.height = 1.1
			var query := PhysicsShapeQueryParameters3D.new()
			query.shape = body
			query.transform.origin = g.global_position + Vector3(0, 1.05, 0)
			var hits := g.get_world_3d().direct_space_state.intersect_shape(query, 1)
			if not hits.is_empty():
				contacts.append({"t": elapsed, "at": row.guide, "object": str(hits[0].collider.get_parent().name)})
			still_for = still_for + 0.5 if g.position.distance_to(last_position) < 0.03 else 0.0
			last_position = g.position
			if still_for > 8.0:
				stuck = true
				print("GUIDE STUCK at ", g.position, " trying ", g.stops[g.i])
				break
		if tick % 12 == 0:
			await physics_frame
		if g.mode == "idle" or (not stops.is_empty() and stops[-1].kind == "cinema"):
			break
	var bad := samples.filter(func(row): return row.angle > 25.0)
	var obstructed := stops.filter(func(row): return not row.subject_visible or row.angle > 10.0)
	var expected: int = game._tour().filter(func(s): return not s.get("via", false) and not s.get("ride", false)).size()
	var report := {"seconds": elapsed, "stops": stops, "walking_samples": samples.size(),
		"wrong_way_samples": bad, "worst_angle": worst, "obstructed_stops": obstructed,
		"expected_stops": expected, "guide_contacts": contacts, "stuck": stuck}
	FileAccess.open(out, FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print("TOUR CAMERA: %d/%d stops, %d obstructed, %d/%d walking samples over 25 degrees, worst %.1f" % [stops.size(), expected, obstructed.size(), bad.size(), samples.size(), worst])
	print("GUIDE CONTACTS: ", contacts.size())
	quit(1 if not bad.is_empty() or not obstructed.is_empty() or stops.size() != expected or not contacts.is_empty() or stuck else 0)


func measure(target: Vector3) -> Dictionary:
	var p: Node3D = game.player
	var cam: Camera3D = p.camera
	var direction := (target - cam.global_position).normalized()
	var angle := rad_to_deg(acos(clampf((-cam.global_basis.z).dot(direction), -1, 1)))
	var ray := PhysicsRayQueryParameters3D.create(cam.global_position, target)
	var hit := cam.get_world_3d().direct_space_state.intersect_ray(ray)
	return {"t": elapsed, "angle": angle, "camera": [p.position.x, p.position.y, p.position.z],
		"guide": [game.guide.position.x, game.guide.position.y, game.guide.position.z],
		"hit_body": str(hit.collider.name) if not hit.is_empty() else "",
		"hit_shape": int(hit.shape) if not hit.is_empty() else -1,
		"blocked_by": str(hit.collider.get_parent().name) if not hit.is_empty() else ""}
