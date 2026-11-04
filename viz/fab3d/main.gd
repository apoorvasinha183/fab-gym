extends Node3D
## The 3D fab and its guide (docs/FAB-3D.md): the campus streamed around the visitor, the simulator running live in the
## helper, the robot CEO's tour through both phases to the cinema, then free exploration. Questions are answered from
## the live run by plain rules first; anything else goes to the helper (Meta's model, through the glossary). From the
## SMT2020 testbed; a gigafab-style layout of our own design; not a real fab.

const Looks := preload("res://looks.gd")
const Solid := preload("res://solid.gd")
@onready var campus: Node3D = $campus
@onready var live: Node = $live
@onready var player: Node3D = $player
@onready var guide: Node3D = $guide
@onready var cinema: Node3D = $cinema
@onready var ui: CanvasLayer = $ui
@onready var building: Node3D = $building
@onready var entrance: Node3D = $entrance
@onready var exterior: Node3D = $exterior
@onready var drone: Node3D = $drone

var clock := 360.0            # simulated minutes since the run began: 06:00 on day 1
var speed := 1.0 / 60.0       # simulated minutes a real second: real time, so vehicles move at their own speed
var _ask_every := 0.0
var staff_scene: PackedScene = preload("res://staff/staff.tscn")
var staff := {}               # tool index -> worker
var check_out := ""
var perf_out := ""
var shots_dir := ""
var film := false
var cues := []                # --cues [FILE] [--cue N]: Lou's lines for the demo video (video/lou-cues.json), ] for the next
var cue_i := -1
var explore := false          # --explore: no tour; the visitor walks the whole fab on their own, into every bay, W A S D to take over
const FILM_AREAS := ["Litho", "Dry_Etch", "Implant", "Diffusion", "Planar", "Wet_Etch"]
const FILM_AREAS_BE := ["TF", "Planar"]
var touring := false
var intro := false            # the drone is flying the opening
var no_intro := false
var _stop_n := 0
var _stop_total := 0
var _t := 0.0
var _frame_ms: PackedFloat32Array = PackedFloat32Array()
var _drawn0 := 0
var _shot_at := [6.0, 14.0, 24.0, 34.0, 46.0]
var corridor := false          # a fixed 6 s walk down the strip from the air shower to the bay, for comparing shimmer
var sweep := false             # a fixed 12 s camera move (outside wall, then the spine) for comparing shimmer
var soft_facade := false
var stop_shots := false        # stills taken at the stops instead of at fixed times
var near_vehicle := false      # shots framed on one vehicle (one lowering its pod if there is one), to check the rail
var _watched := -1
var _clear_out := ""           # --clearance FILE: the camera's lowest height over the cinema's floor
var _clear_min := 1e9
var lou_brain := true          # Lou answers with Muse Spark Open (docs/FAB-3D.md, F11); --no-lou keeps the floor's own rules
var _lou_waiting := false
var _lou_q := ""
var _lou_walk_was := -1.0      # the guide's walking speed before Lou set off briskly
var _lou_ask := ""             # --lou-ask QUESTION: asked a few seconds into the tour, for checking


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if "--check" in args:
		check_out = args[args.find("--check") + 1]
	if "--perf" in args:
		perf_out = args[args.find("--perf") + 1]
	explore = "--explore" in args
	if "--cues" in args:
		var at := args.find("--cues") + 1
		var path := ProjectSettings.globalize_path("res://").path_join("../../video/lou-cues.json")
		if at < args.size() and not str(args[at]).begins_with("--"):
			path = str(args[at])
		var got = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
		cues = got["cues"] if got is Dictionary and got.has("cues") else []
		if "--cue" in args:
			cue_i = int(args[args.find("--cue") + 1]) - 2
		print("fab3d: %d cues from %s" % [cues.size(), path])
	if "--film" in args:
		film = true
	if "--shots" in args:
		shots_dir = args[args.find("--shots") + 1]
	if "--clearance" in args:
		_clear_out = args[args.find("--clearance") + 1]
	near_vehicle = "--near-vehicle" in args
	no_intro = "--no-intro" in args or near_vehicle or explore
	sweep = "--sweep" in args
	corridor = "--corridor" in args
	if "--no-ssao" in args:
		$environment.environment.ssao_enabled = false
	if "--taa" in args:
		get_viewport().use_taa = true
	soft_facade = "--soft-facade" in args
	# the film keeps its scripted answer unless --lou asks the brain
	lou_brain = not ("--no-lou" in args) and (not film or "--lou" in args)
	if "--lou-ask" in args:
		_lou_ask = args[args.find("--lou-ask") + 1]
	guide.trace = "--trace-walk" in args
	if "--no-ui" in args:
		ui.visible = false               # clean stills, for designing the screen over them
	stop_shots = "--stop-shots" in args
	if stop_shots:
		_shot_at = [1e9]
	if "--shot-times" in args:
		_shot_at = []
		for t in args[args.find("--shot-times") + 1].split(","):
			_shot_at.append(float(t))
	campus.viewer = player
	cinema.viewer = player
	cinema.guide = guide
	player.setup(campus.data)
	cinema.setup(campus.data.get("cinema", {}))
	cinema.autoplay = false
	if film:
		cinema.video.finished.connect(func() -> void:
			print("fab3d: recorded movie finished naturally")
			get_tree().create_timer(2.0).timeout.connect(func() -> void: get_tree().quit()))
	cinema.prompt.connect(func(t: String) -> void: ui.show_prompt(t))
	guide.line_of = Callable(self, "_line_for")
	guide.planner = Callable(self, "_plan_leg")
	guide.snapper = Callable(self, "reach")
	guide.said.connect(func(t: String) -> void: ui.show_line(t))
	guide.arrived.connect(_on_arrived)
	guide.tour_done.connect(_free_walk)
	live.run_ready.connect(_on_run)
	live.state.connect(_on_state)
	live.answered.connect(_on_answer)
	live.heard.connect(_on_heard)
	live.lou_replied.connect(_on_lou)
	live.failed.connect(func(where: String, m: String) -> void: ui.show_line("[i]%s[/i]" % m))
	ui.asked.connect(handle_question)
	ui.recorded.connect(func(wav: PackedByteArray) -> void: live.voice(wav))
	ui.speed_changed.connect(func(s: float) -> void: speed = s)
	ui.free_walk.connect(_free_walk)
	ui.advance.connect(func() -> void:
		if intro:
			drone.finish()
		else:
			guide.skip())
	_dress_building()
	exterior.setup(campus.data["exterior"])
	drone.setup(campus.data["drone"], player)
	drone.line.connect(func(t: String) -> void: ui.show_line(t))
	drone.done.connect(_after_intro)
	entrance.setup(campus.data["entrance"])
	entrance.rider = guide
	guide.viewer = player
	guide.shower_box = campus.data["entrance"]["permit"]["air_shower"]["box"]
	player.lift = campus.data["entrance"]["permit"]["lift"]["box"]
	player.lift_car = entrance.car
	_solids()
	# the tour starts in the parking lot, the visitor a few steps behind the CEO
	var lot: Array = campus.data["entrance"]["route"][0]["at"]
	guide.global_position = _at(lot)
	guide.rotation.y = PI / 2
	player.place(float(lot[0]) - 5.0, float(lot[1]), -PI / 2)
	print("fab3d: ready; shots=", shots_dir, " perf=", perf_out, " check=", check_out)
	if check_out != "":
		_check.call_deferred()
		return
	live.start(1, 1.0)


# ------------------------------------------------------------------ the guide's paths around what is solid

var nav_ready := false
signal nav_baked
var _nav: NavigationRegion3D
var _body := CapsuleShape3D.new()


func _bake_nav() -> void:
	# a walkable map of the campus from what is solid (its floors, walls, tools), baked once on a worker thread
	for n in [building, entrance, exterior, cinema, get_node("solid_tools")]:
		n.add_to_group("nav_source")
	var nm := NavigationMesh.new()
	nm.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nm.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_GROUPS_WITH_CHILDREN
	nm.geometry_source_group_name = "nav_source"
	nm.cell_size = 0.2
	nm.cell_height = 0.1
	nm.agent_radius = 0.4
	nm.agent_height = 2.0
	nm.agent_max_climb = 0.3
	nm.agent_max_slope = 30.0
	# only where the tour goes: the lot and entrance, both phases and the bridge, the cinema
	nm.filter_baking_aabb = AABB(Vector3(-60.0, -1.0, -75.0), Vector3(580.0, 12.0, 205.0))
	_nav = NavigationRegion3D.new()
	_nav.navigation_mesh = nm
	add_child(_nav)
	var map := get_world_3d().navigation_map
	NavigationServer3D.map_set_cell_size(map, 0.2)
	NavigationServer3D.map_set_cell_height(map, 0.1)
	_nav.bake_finished.connect(func() -> void:
		# the map takes the new mesh at a later sync: wait until it answers
		for k in 300:
			await get_tree().physics_frame
			if NavigationServer3D.map_get_closest_point(map, Vector3(3.5, 7.5, -1.0)) != Vector3.ZERO:
				break
		nav_ready = true
		guide.planning = true
		print("fab3d: walkable map baked, %d polygons, %.1f s after start" % [nm.get_polygon_count(), Time.get_ticks_msec() / 1000.0])
		nav_baked.emit())
	_nav.bake_navigation_mesh(true)


func leg_hit(a: Vector3, b: Vector3) -> String:
	# sweep the guide's body (0.25 m round, from knee to head) along a leg; "" if nothing solid is in the way
	var q := PhysicsShapeQueryParameters3D.new()
	_body.radius = 0.25
	_body.height = 1.2
	q.shape = _body
	var space := get_world_3d().direct_space_state
	var n := int(ceil(a.distance_to(b) / 0.5))
	for j in n:
		var p := a.lerp(b, float(j) / n)
		var r := a.lerp(b, float(j + 1) / n)
		# his feet: the floor under him in the cinema (exact there), else the route's own height
		var feet: float = player.floor_at(p.x, -p.z) if player.in_cinema(p.x, -p.z) else p.y - 0.1
		q.transform = Transform3D(Basis(), Vector3(p.x, feet + 0.5 + _body.height / 2.0, p.z))
		q.motion = Vector3(r.x - p.x, 0.0, r.z - p.z)
		if space.cast_motion(q)[0] < 1.0:
			q.transform.origin += q.motion * space.cast_motion(q)[1]
			var info := space.get_rest_info(q)
			var obj = instance_from_id(int(info.get("collider_id", 0)))
			var what := str(obj.get_parent().name) if obj and obj.get_parent() else "?"
			return "at (%.1f, %.1f) touching %s" % [p.x, -p.z, what]
	return ""


func reach(a: Vector3, b: Vector3) -> Vector3:
	# a corner of the route that cannot be reached from a (it stands inside something solid) moves to the nearest
	# spot that can, within 4 m
	if not nav_ready or leg_hit(a, b) == "":
		return b
	var p := NavigationServer3D.map_get_path(get_world_3d().navigation_map, a, b, true)
	if p.size() < 2:
		return b
	var e: Vector3 = p[-1]
	var d := Vector2(e.x - b.x, e.z - b.z).length()
	return Vector3(e.x, b.y, e.z) if d > 0.3 and d < 4.0 else b


func _plan_leg(a: Vector3, b: Vector3) -> Array:
	# the corners of a path around whatever blocks the straight leg; none when it is clear or no path is known
	if not nav_ready or leg_hit(a, b) == "":
		return []
	var map := get_world_3d().navigation_map
	var p := NavigationServer3D.map_get_path(map, a, b, true)
	if p.size() < 2 or Vector2(p[-1].x - b.x, p[-1].z - b.z).length() > 0.6:
		return []
	var out := []
	for k in range(1, p.size() - 1):
		var c: Vector3 = p[k]
		out.append(Vector3(c.x, lerpf(a.y, b.y, float(k) / (p.size() - 1)), c.z))
	return out


func _solids() -> void:
	# everything solid (solid.gd): the visitor slides along it, the camera stays in front of it, the guide's route clears it
	Solid.meshes(building)
	var moving := [entrance.car]
	for dr in entrance.doors:
		moving.append(dr[0])                 # the lift's sliding leaves
	Solid.meshes(entrance, moving)
	Solid.meshes(exterior)
	var cz := float(campus.data["heights"]["clean_z"])
	var list := []
	for t in campus.data["tools"]:
		var h := float(t[8])
		list.append([Vector3((float(t[4]) + float(t[5])) / 2.0, cz + h / 2.0, -(float(t[6]) + float(t[7])) / 2.0),
				Vector3((float(t[5]) - float(t[4])) * 0.98, h, (float(t[7]) - float(t[6])) * 0.98), 0.0])
	for st in campus.data["stockers"]:
		list.append([Vector3((float(st[0]) + float(st[1])) / 2.0, cz + 1.75, -(float(st[2]) + float(st[3])) / 2.0),
				Vector3(float(st[1]) - float(st[0]), 3.5, float(st[3]) - float(st[2])), 0.0])
	Solid.boxes(self, list, "solid_tools")
	_bake_nav.call_deferred()


func _dress_building() -> void:
	# a cleanroom's surfaces: raised-floor tiles of 0.6 m with perforations (air goes down through them), a ceiling of
	# 1.2 m filter units glowing white, white wall panels, white-clad columns. Sizes assumed.
	var C := campus
	var looks := {
		"flooring": C.panel_mat(Color(0.8, 0.82, 0.84), Color(0.74, 0.76, 0.79), Vector3(0.6, 0.6, 0.6), 0.02, 0, 0.0, 0.45),
		"ceiling": C.panel_mat(Color(0.97, 0.98, 1.0), Color(0.88, 0.9, 0.92), Vector3(1.2, 1.2, 1.2), 0.03, 0, 0.45, 0.6),
		# inside walls and columns plain: panel seams finer than a pixel crawled as the camera moved
		"wall": _plain(Color(0.93, 0.94, 0.95), 0.5),
		"column": _plain(Color(0.9, 0.91, 0.93), 0.5),
	}
	# outside: ribbed metal cladding on the fabs' outer walls, gravel ballast on the flat roofs, concrete underneath
	# (CC0 texture sets; sizes assumed)
	# the outside: large flat insulated panels with faint seams. Ribbed cladding (CC0 metal sheet) shimmered even softened
	# and under temporal AA, its ribs finer than a pixel at a distance (measured 3 Nov), so the outside carries no rib
	var clad: StandardMaterial3D = C.panel_mat(Color(0.9, 0.91, 0.92), Color(0.82, 0.84, 0.86), Vector3(3.0, 4.0, 3.0), 0.01, 0, 0.0, 0.55)
	var outside := {"wall_outer": clad,
			"slab_roof": Looks.pbr("gravel_concrete", 3.0, Color(0.78, 0.79, 0.8), -1.0, "grey", true),
			"slab_floor": Looks.pbr("smooth_concrete_floor", 4.0)}
	for mi in building.find_children("*", "MeshInstance3D", true, false):
		var done := false
		for k in outside.keys():
			if str(mi.name).contains(k):
				mi.material_override = outside[k]
				done = true
		if done:
			continue
		for k in looks.keys():
			if str(mi.name).contains(k):
				mi.material_override = looks[k]
	# the wall mesh holds two surfaces: the cleanroom's inside faces and the clad outside faces
	for mi in building.find_children("*wall*", "MeshInstance3D", true, false):
		mi.material_override = null
	Looks.dress(building, {"bim_wall": looks["wall"], "bim_wall_outer": outside["wall_outer"]})
	# inside the fabs the sun does nothing (the roof is over it) except self-shadow the walls in fine crawling stripes:
	# inside surfaces go on render layer 2, which the sun does not light (main.tscn: the sun's cull mask)
	for mi in building.find_children("*", "MeshInstance3D", true, false):
		var nm := str(mi.name)
		if (nm.contains("wall") and not nm.contains("outer")) or nm.contains("flooring") or nm.contains("ceiling") \
				or nm.contains("column") or nm.contains("slab_floor"):
			mi.layers = 2
	$ground.material_override = Looks.pbr("leafy_grass", 3.5, Color(0.42, 0.62, 0.3), -1.0, "grey", true)


# ------------------------------------------------------------------ the run and the clock

func _on_run(info: Dictionary) -> void:
	if not no_intro and check_out == "":
		# the opening flight over the campus first; the tour starts when it lands (or the visitor skips it)
		intro = true
		campus.paused = true
		player.follow = null
		player.roaming = false
		ui.set_stop(0, 0, "Fab Gym from the air")
		drone.start()
		return
	_start_tour()


func _start_explore() -> void:
	# a visitor walks the whole fab on their own: down phase one's spine, into each bay to look, over the bridge, and
	# down phase two's; W A S D takes over at any moment
	if not nav_ready:
		await nav_baked
	touring = false
	intro = false
	campus.paused = false
	var z := float(campus.heights["clean_z"])
	guide.visible = false
	guide.set_process(false)
	player.follow = null
	player.roaming = true
	player.fly = false
	player.place(4.0, 0.0, -PI / 2)
	# no one is talking: the text window and portrait stay closed
	ui.line_label.text = ""
	ui.line_label.visible_characters = -1
	ui._done_for = 99.0
	ui.set_stop(0, 0, "Exploring the fab  ·  W A S D to take over")
	var targets := []
	for phase in [0, 1]:
		var here := []
		for c in campus.data["labels"]:
			if (float(c[1]) < 261.8) == (phase == 0):
				here.append(c)
		here.sort_custom(func(a, b): return float(a[1]) < float(b[1]))
		for c in here:
			var x := float(c[1])
			var side := 1.0 if float(c[2]) > 0 else -1.0
			targets.append({"at": Vector3(x, z, 0.0)})
			targets.append({"at": Vector3(x, z, -side * 9.0), "look": Vector3(x, z + 1.2, -side * 30.0), "hold": 2.5,
					"label": str(c[0])})
			targets.append({"at": Vector3(x, z, 0.0), "look": Vector3(x + 20.0, z + 1.6, 0.0), "hold": 0.6})
		if phase == 0:
			for p in [Vector3(255.0, z, 0.0), Vector3(285.8, z, 0.0), Vector3(316.0, z, 0.0)]:
				targets.append({"at": p})
	# each leg along the walkable floor, so it goes round tools and through doorways
	var map := get_world_3d().navigation_map
	var route := []
	var from := Vector3(4.0, z, 0.0)
	for t in targets:
		# onto the walkable floor: a bay's stop sits in its aisle, clear of the tools
		var snapped := NavigationServer3D.map_get_closest_point(map, t["at"])
		if snapped.distance_to(t["at"]) > 6.0:
			continue
		t["at"] = snapped
		if t.has("label"):
			# look down the bay's own aisle, so the pause shows its tools and not a tool's side panel
			var far := NavigationServer3D.map_get_closest_point(map, t["look"])
			t["look"] = far + Vector3(0.0, 1.3, 0.0) if far.distance_to(snapped) > 8.0 else t["look"]
		var path := NavigationServer3D.map_get_path(map, from, t["at"], true)
		for k in range(1, path.size() - 1):
			route.append({"at": path[k]})
		route.append(t)
		from = t["at"]
	player.autopilot = route
	player.autopilot_at.connect(func(w: Dictionary) -> void:
		if w.has("label"):
			ui.set_stop(0, 0, "Exploring  ·  " + str(w["label"]))
			print("fab3d: explore looking at ", w["label"], " ", Vector2(player.global_position.x, -player.global_position.z)))
	player.autopilot_done.connect(func() -> void:
		ui.set_stop(0, 0, "Walk alone  ·  W A S D")
		print("fab3d: explore finished at ", Vector2(player.global_position.x, -player.global_position.z), " after %.0f s" % _t)
		if shots_dir != "":
			get_tree().create_timer(3.0).timeout.connect(func() -> void: get_tree().quit()))
	print("fab3d: explore started, %d points" % route.size())

func _after_intro() -> void:
	intro = false
	campus.paused = false
	_start_tour()


func _start_tour() -> void:
	if "--aisle" in OS.get_cmdline_user_args():
		# the video: Lou on the clear central aisle of phase one, the visitor a few steps behind him; he speaks, is
		# asked a question, and walks there along the aisle
		if not nav_ready:
			await nav_baked
		touring = false
		intro = false
		campus.paused = false
		var z := float(campus.heights["clean_z"])
		guide.visible = true
		guide.global_position = Vector3(24.0, z, 0.0)
		guide.rotation.y = PI / 2       # facing the visitor while he makes his promise
		player.place(31.0, 0.0, PI / 2)
		player.roaming = false
		player.follow = guide
		player._dir_x = -1.0       # he walks west, down the aisle, so the camera keeps behind him from the first step
		ui.line_label.text = ""
		ui.set_stop(0, 0, "Phase one · the main aisle")
		var ua := OS.get_cmdline_user_args()
		if "--say" in ua and not cues.is_empty():
			var n := clampi(int(ua[ua.find("--say") + 1]) - 1, 0, cues.size() - 1)
			get_tree().create_timer(1.0).timeout.connect(func() -> void: ui.show_line(str(cues[n]["text"])))
		if _lou_ask != "":
			get_tree().create_timer(5.5).timeout.connect(func() -> void: handle_question(_lou_ask))
		return
	if "--seat" in OS.get_cmdline_user_args():
		# the video: straight to a seat in the cinema, the film playing on its screen
		touring = false
		intro = false
		guide.visible = false
		cinema.sit("R5C4")
		get_tree().create_timer(1.0).timeout.connect(func() -> void: cinema.play())
		return
	if explore:
		_start_explore()
		return
	ui.show_line("The run is ready: %d tools, the simulator's day from 06:00. Follow me." % campus.data["tools"].size())
	touring = true
	_stop_n = 0
	_stop_total = 0
	if film:
		guide.speed = 7.0
		guide.talk_scale = 0.62
	player.roaming = false
	player.follow = guide
	var tour := _tour()
	if "--cinema" in OS.get_cmdline_user_args():
		# start at the cinema door, for checking that part of the tour
		var k := tour.find(tour.filter(func(st): return st["kind"] == "cinema_door")[0])
		tour = tour.slice(k)
		guide.global_position = tour[0]["at"]
	var args := OS.get_cmdline_user_args()
	if "--device-stop" in args:
		var area: String = args[args.find("--device-stop") + 1]
		for index in tour.size():
			if tour[index].get("area", "") == area:
				tour = tour.slice(index)
				guide.global_position = tour[0]["at"]
				player.global_position = guide.global_position + Vector3(-7.0, 1.75, guide.global_position.z * -1.0)
				break
	for st in tour:
		if not st.get("via", false) and not st.get("ride", false):
			_stop_total += 1
	guide.start(tour)
	var say_at := OS.get_cmdline_user_args().find("--say")
	if say_at >= 0 and not cues.is_empty():
		# the video: Lou's cue N in his window as the fab appears
		var n := clampi(int(OS.get_cmdline_user_args()[say_at + 1]) - 1, 0, cues.size() - 1)
		get_tree().create_timer(1.5).timeout.connect(func() -> void: ui.show_line(str(cues[n]["text"])))
	if _lou_ask != "":
		get_tree().create_timer(7.0 if say_at >= 0 else 4.0).timeout.connect(func() -> void: handle_question(_lou_ask))


func _process(dt: float) -> void:
	_t += dt
	if _clear_out != "" and player.in_cinema(player.global_position.x, -player.global_position.z):
		# the camera's lowest height over the floor under it, while in the cinema (it must never sink into a step)
		var c: float = player.global_position.y - player.floor_at(player.global_position.x, -player.global_position.z)
		if c < _clear_min:
			_clear_min = c
			var f := FileAccess.open(_clear_out, FileAccess.WRITE)
			f.store_string(JSON.stringify({"lowest_m": c, "at": [player.global_position.x, -player.global_position.z], "t": _t}))
			f.close()
	if sweep:
		_sweep()
	if corridor:
		_corridor()
	if near_vehicle and live.run_id != "":
		_watch_vehicle()
	if shots_dir != "" and not _shot_at.is_empty() and _t >= _shot_at[0]:
		_shot_at.pop_front()
		var path := "%s/shot-%02d.png" % [shots_dir, int(_t)]
		var err := get_viewport().get_texture().get_image().save_png(path)
		var shown := 0
		for v in campus.carriers.keys():
			if campus.carriers[v]["node"].visible:
				shown += 1
		print("shot ", path, " ", err, " cells ", campus.loaded.size(), " tools ", campus.tool_nodes.size(), " carriers ", shown, " of ", campus.stays.size(), " stays, run ", live.run_id)
		if _shot_at.is_empty():
			get_tree().quit()
	if perf_out != "" and live.run_id != "":
		if _frame_ms.is_empty():
			_drawn0 = Engine.get_frames_drawn()
		_frame_ms.append(dt * 1000.0)
		if _frame_ms.size() >= 3600:
			_write_perf()
	ui.talking = (intro or guide.mode == "talk") and not explore
	if live.run_id != "":
		clock += dt * speed
		campus.clock = clock
		ui.set_clock(clock, speed)
		_ask_every -= dt
		if _ask_every <= 0.0:
			_ask_every = 1.0
			live.ask_state(clock, campus.full_ids, max(2.0, speed * 2.0))
	# lift the roof and the filter ceiling away when the visitor flies above them
	var above := player.global_position.y > 17.0 and not intro
	for c in building.find_children("*roof*", "", true, false) + building.find_children("*ceiling*", "", true, false):
		c.visible = not above


func _sweep() -> void:
	# 0 to 6 s: along the west wall outside, eye height, looking at it; 6 to 12 s: down the spine inside
	player.roaming = false
	player.follow = null
	if _t < 6.0:
		var y := lerpf(10.0, 40.0, _t / 6.0)
		player.global_position = Vector3(-34.0, 1.75, -y)
		player.yaw = -PI / 2.0 + 0.25
		player.pitch = 0.12
	elif _t < 12.0:
		if not _swept_in:
			_swept_in = true
			player.global_position = Vector3(60.0, 9.25, 0.0)
			campus.update_cells(true)
		player.global_position = Vector3(lerpf(60.0, 78.0, (_t - 6.0) / 6.0), 9.25, 0.0)
		player.yaw = -PI / 2.0
		player.pitch = 0.0
	elif _t < 15.0:
		pass                            # 12 to 15 s: held still inside, for counting pixels that flicker
	else:
		get_tree().quit()


var _swept_in := false


func _corridor() -> void:
	player.roaming = false
	player.follow = null
	if _t < 6.0:
		player.global_position = Vector3(1.2, 9.1, -lerpf(19.0, 4.0, _t / 6.0))
		player.yaw = 0.15
		player.pitch = -0.05
	else:
		get_tree().quit()


func _watch_vehicle() -> void:
	var cs: Dictionary = campus.carriers
	if not cs.has(_watched) or not cs[_watched]["node"].visible:
		_watched = -1
		var best := 1e9
		for v in cs.keys():
			if not cs[v]["node"].visible:
				continue
			var dist: float = cs[v]["node"].global_position.distance_to(guide.global_position) - (50.0 if cs[v]["belts"].visible else 0.0)
			if dist < best:
				best = dist
				_watched = v
	if _watched < 0:
		return
	var at: Vector3 = cs[_watched]["node"].global_position
	player.roaming = false
	player.follow = null
	player.global_position = at + Vector3(4.5, -1.2, 4.5)
	var d := at + Vector3(0, -0.8, 0) - player.global_position
	player.yaw = atan2(-d.x, -d.z)
	player.pitch = atan2(d.y, Vector2(d.x, d.z).length())


func _on_state(d: Dictionary) -> void:
	campus.apply_state(d)
	_place_staff()


func _place_staff() -> void:
	# a maintenance worker kneels at each tool that is down nearby; operators stand at a few working tools
	var want := {}
	var operators := 0
	for i in campus.tool_nodes.keys():
		var m := str(campus.moods.get(i, ""))
		if m in ["hurt", "physio"] and want.size() < 10:
			want[i] = ["maintenance", "Fixing_Kneeling"]
		elif m == "work" and operators < 6 and int(i) % 17 == 0:
			want[i] = ["operator", "Idle_Loop"]
			operators += 1
	for i in staff.keys():
		if not want.has(i) or not campus.tool_nodes.has(i):
			staff[i].queue_free()
			staff.erase(i)
	for i in want.keys():
		if staff.has(i):
			continue
		var tool: Node3D = campus.tool_nodes[i]
		var w: Node3D = staff_scene.instantiate()
		add_child(w)
		campus.inside(w)
		var front := tool.global_transform.basis.z.normalized()
		var t: Array = campus.data["tools"][i]
		var reach := maxf(float(t[5]) - float(t[4]), float(t[7]) - float(t[6])) / 2.0
		w.global_position = tool.global_position + front * (reach + 0.9)
		w.rotation.y = tool.rotation.y + PI
		w.dress(want[i][0], want[i][1])
		staff[i] = w


# ------------------------------------------------------------------ the tour

func _at(p: Array) -> Vector3:
	# a route point (plan x, y, z) to the scene; ground points sit on the paving
	var z := float(p[2])
	return Vector3(float(p[0]), z if z > 1.0 else 0.1, -float(p[1]))


func _device_for(area: String, phase: int, at: Vector2) -> Dictionary:
	# Choose a real tool at the mouth of this bay, on this side and in this phase.
	var best := -1
	var score := INF
	for i in campus.data["tools"].size():
		var t: Array = campus.data["tools"][i]
		var centre := Vector2((float(t[4]) + float(t[5])) / 2.0, (float(t[6]) + float(t[7])) / 2.0)
		if str(t[1]) != area or int(t[3]) != phase or signf(centre.y) != signf(at.y):
			continue
		var distance := centre.distance_to(Vector2(at.x, signf(at.y) * 4.0))
		if distance < score:
			score = distance
			best = i
	if best < 0:
		return {}
	var t: Array = campus.data["tools"][best]
	return {"tool": best, "target": Vector3((float(t[4]) + float(t[5])) / 2.0,
		float(campus.heights["clean_z"]) + float(t[8]) * 0.5 - 0.35, -(float(t[6]) + float(t[7])) / 2.0)}


func _tour() -> Array:
	var z := float(campus.heights["clean_z"])
	var stops: Array = []
	# from the parking lot through gowning to the cleanroom (docs/FAB-3D.md, F9)
	for r in campus.data["entrance"]["route"]:
		var st := {"kind": str(r["kind"]), "at": _at(r["at"])}
		if r.get("via", false):
			st["via"] = true
		else:
			st["face_viewer"] = true       # on the way in, the CEO turns to talk to you
		if r.get("ride", false):
			st["ride"] = true
		if r.get("bump", false):
			st["bump"] = true
		stops.append(st)
	var seen := {}
	var labels: Array = campus.data["labels"].duplicate()
	labels.sort_custom(func(a, b) -> bool: return float(a[1]) < float(b[1]))
	for phase in [0, 1]:
		for l in labels:
			var x := float(l[1])
			var in_p1 := x < 261.8
			if (phase == 0) != in_p1 or seen.has([phase, str(l[3])]):
				continue
			if film and not (str(l[3]) in (FILM_AREAS if phase == 0 else FILM_AREAS_BE)):
				continue
			seen[[phase, str(l[3])]] = true
			var side := 1.0 if float(l[2]) > 0 else -1.0
			stops.append({"kind": "area", "area": str(l[3]), "label": str(l[0]), "at": Vector3(x, z, -side * 5.0),
					"face": PI if side > 0 else 0.0, "plan": Vector2(x, float(l[2])),
					"device": _device_for(str(l[3]), phase, Vector2(x, float(l[2])))})
		if phase == 0:
			# through the doorway in phase one's end wall, onto the bridge, and through phase two's
			stops.append({"kind": "via", "via": true, "at": Vector3(255.0, z, 0.0)})
			stops.append({"kind": "bridge", "at": Vector3(285.8, z, 0.0), "face": -PI / 2})
			stops.append({"kind": "via", "via": true, "at": Vector3(316.0, z, 0.0)})
	# the cinema (data/cinema/plan.json): in by the main entrance, across the lobby, up the ramp, onto the mid cross aisle
	stops.append({"kind": "cinema_door", "at": Vector3(58.0, 0.1, 92.0), "face": PI, "teleport": true})
	# through the sliding doors, down the lobby clear of the benches and posters, up the ramp, through the ramp door,
	# and out along the mid cross aisle; he stops beside it, turned to the visitor
	for p in [[58.0, -99.5, 0.1], [58.0, -105.4, 0.1], [69.2, -105.4, 0.1], [69.2, -109.1, 0.1], [61.2, -109.1, 0.7],
			[59.7, -109.1, 0.7], [52.5, -109.1, 1.3], [52.3, -109.1, 1.3], [52.3, -110.8, 1.3]]:
		stops.append({"kind": "via", "via": true, "at": Vector3(p[0], p[2], -p[1])})
	stops.append({"kind": "cinema", "at": Vector3(51.1, 1.3, 114.4), "face": 0.68})
	return stops


func _on_arrived(s: Dictionary) -> void:
	if s["kind"] == "lou":
		ui.set_stop(0, 0, str(s["label"]))
		if _lou_walk_was >= 0.0:
			guide.speed = _lou_walk_was
			_lou_walk_was = -1.0
		print("fab3d: lou arrived at ", s["area"], " ", Vector2(guide.global_position.x, -guide.global_position.z))
		if shots_dir != "":
			_shot_at.append(_t + 2.5)
			_shot_at.append(_t + 7.0)
			_shot_at.sort()
		if _lou_ask != "":
			get_tree().create_timer(9.0).timeout.connect(func() -> void: get_tree().quit())
		return
	if not s.get("via", false) and not s.get("ride", false):
		_stop_n += 1
		ui.set_stop(_stop_n, _stop_total, _stop_title(s))
	if shots_dir != "" and stop_shots and s.get("face_viewer", false):
		# a still a few seconds after each stop on the way in, so the stills follow the tour whatever the run's start;
		# the cleanroom is the last
		_shot_at.append(_t + 3.0)
		if s["kind"] == "cleanroom":
			_shot_at.erase(1e9)
		_shot_at.sort()
	if s["kind"] == "air_shower":
		entrance.jets(true)
		get_tree().create_timer(4.5).timeout.connect(func() -> void: entrance.jets(false))
	if film and s["kind"] == "area" and str(s["area"]) == "Planar" and s["plan"].x < 261.8:
		# the film's one question, typed into the box and answered from the live run
		guide.hold = 9.0
		get_tree().create_timer(3.5).timeout.connect(func() -> void: ui.ask_box.text = "why is this queue long?")
		get_tree().create_timer(5.0).timeout.connect(func() -> void:
			ui.ask_box.text = ""
			handle_question("why is this queue long?"))
	if s.get("teleport", false):
		player._trail.clear()
		player.global_position = s["at"] + Vector3(0, 2.6, -4.5)
	if s["kind"] == "cinema":
		# the visitor walks to a seat of their own; the recorded film sits in row 5 and the film starts by itself
		player.follow = null
		if film:
			player.roaming = true
			cinema.sit("R5C4")
			# Establish the seated view, then start at the beginning in full screen.
			get_tree().create_timer(2.0).timeout.connect(func() -> void:
				cinema.play()
				cinema.fullscreen(true)
				print("fab3d: recorded movie started from seat"))
		else:
			# the camera walks on to the middle of the aisle and turns to the screen
			player.glide(Vector3(52.4, player.floor_at(52.4, -116.0) + 1.65, 116.0), PI / 2.0, -0.05, 2.5)


func _stop_title(s: Dictionary) -> String:
	match str(s["kind"]):
		"lot": return "The parking lot"
		"pavilion": return "Visitors' entrance"
		"lift": return "The lift"
		"gowning": return "Gowning room"
		"air_shower": return "Air shower"
		"cleanroom": return "The cleanroom"
		"area", "lou": return str(s.get("label", ""))
		"bridge": return "The bridge"
		"cinema_door": return "To the cinema"
		"cinema": return "The cinema"
	return ""


func _free_walk() -> void:
	ui.set_stop(0, 0, "Walking alone")
	touring = false
	player.follow = null
	player.roaming = true
	guide.mode = "idle"


func _line_for(s: Dictionary) -> String:
	match s["kind"]:
		"area", "lou":
			return _area_line(str(s["area"]), s["plan"], str(s["label"]))
		"bridge":
			return "This bridge joins the front end to the copper back end. Copper must never reach the front-end tools, so lots bound for the back end ride copper carriers, the orange ones. Fabs do this in different ways; a separate building is the strict one."
		"lot":
			return "Welcome to the fab. I'm Lou Latency, the CEO. Sorry for the wait, I'm still loading. We park out here and walk in. Everything you'll see inside is the simulator's day as it runs, from six this morning."
		"pavilion":
			return "This is the visitors' entrance. The cleanroom is a floor up. The level under it, the sub-fab, holds the pumps, power and chemical lines that feed every tool above."
		"lift":
			return "We take the lift up to the clean floor. It's the only thing in this building that responds faster than me. Nobody walks into the cleanroom straight from outside: first we gown."
		"gowning":
			return "The gowning room. People shed skin flakes and hair all the time, so you cover up, usually top to bottom: hood, coverall, boots, then gloves. Your street clothes stay in the lockers."
		"air_shower":
			return "The air shower. Jets of filtered air blow loose dust off you, and the far door stays shut until the near one has closed. I don't gown: the suit holds in skin and hair, and I have neither, so I get wiped down."
		"cleanroom":
			return "And we're in. Air comes down through the filters in the ceiling and leaves through the holes in the floor, so dust is carried down and away from the wafers. Let's walk the line."
		"cinema_door":
			return "That's both phases. Before you explore on your own, come and see how a chip is made, from sand to a finished chip."
		"cinema":
			return "Pick any free seat: walk up to it and press E to sit. Once you're in, press Enter and the film fills the screen. Afterwards, walk anywhere: click a tool for its card, or ask me anything."
	return ""


func _area_line(area: String, at: Vector2, label: String) -> String:
	var st: Dictionary = campus.stage_of(area)
	var what := str(st.get("what", "")).split(". ")[0].trim_suffix(".")
	var n := 0
	var working := 0
	var down := 0
	var groups := {}
	for i in campus.tool_nodes.keys():
		var t: Array = campus.data["tools"][i]
		if str(t[1]) != area:
			continue
		var c := Vector2((float(t[4]) + float(t[5])) / 2.0, (float(t[6]) + float(t[7])) / 2.0)
		if c.distance_to(at) > 45.0:
			continue
		n += 1
		groups[str(t[0])] = true
		var m := str(campus.moods.get(i, ""))
		if m in ["work", "tired", "full"]:
			working += 1
		elif m in ["hurt", "physio", "pm"]:
			down += 1
	var waiting := 0
	for g in groups.keys():
		waiting += int(campus.queues.get(g, 0))
	var live_part := ""
	if n > 0 and campus.moods.size() > 0:
		live_part = " Right now %d of these %d tools are working%s, and %d lots are waiting for them." % [
				working, n, (", %d are down or in maintenance" % down) if down > 0 else "", waiting]
	return "%s. %s.%s" % [label, what, live_part]


# ------------------------------------------------------------------ questions

func handle_question(q: String) -> void:
	ui.show_line("[i]You asked:[/i] %s" % q)
	if lou_brain and live.run_id != "" and not _lou_waiting:
		# Lou's Meta brain: Muse Spark Open reads the live run and says what to say and where to go; the helper checks
		# every number against the run before Lou says it
		_lou_waiting = true
		_lou_q = q
		ui.show_line("[i]You asked:[/i] %s\n[i]Lou is thinking (Muse Spark Open)...[/i]" % q)
		guide.get_node("bubble").text = "Thinking... Muse Spark Open"
		live.lou(q, clock, _near_area())
		return
	_rule_answer(q)


func _rule_answer(q: String) -> void:
	# the floor's own rules: used when the brain is off, out of budget, or its reply fails the checks twice
	var s := q.to_lower()
	var area := _area_in(s)
	if (s.begins_with("show me") or s.begins_with("take me") or s.begins_with("where is") or s.begins_with("go to")) and area != "":
		var l := _label_of(area)
		if not l.is_empty():
			var side := 1.0 if float(l[2]) > 0 else -1.0
			player.follow = null
			player.roaming = true
			player.place(float(l[1]) - 8.0, side * 2.0, -PI / 2)
			guide.global_position = Vector3(float(l[1]) - 3.0, float(campus.heights["clean_z"]), -side * 5.0)
			guide.rotation.y = PI if side > 0 else 0.0
			guide.say(_area_line(area, Vector2(float(l[1]), float(l[2])), str(l[0])))
			return
	if s.contains("why") and (s.contains("queue") or s.contains("wait") or s.contains("long") or s.contains("slow") or s.contains("stuck")):
		guide.say(_why_line(area))
		return
	if (s.begins_with("what is") or s.begins_with("what's") or s.begins_with("what does") or s.begins_with("explain")) and area != "":
		var st: Dictionary = campus.stage_of(area)
		if not st.is_empty():
			guide.say("%s: %s %s" % [st["name"], st["what"], st["why"]])
			return
	live.ask(q)


func _why_line(area: String) -> String:
	# the longest queue among the groups near the visitor (or in the area named), and how many of its tools are down
	var here := Vector2(player.global_position.x, -player.global_position.z)
	var best := ""
	var best_q := -1
	var tools_of := {}
	for i in campus.tool_nodes.keys():
		var t: Array = campus.data["tools"][i]
		if area != "" and str(t[1]) != area:
			continue
		if area == "" and Vector2((float(t[4]) + float(t[5])) / 2.0, (float(t[6]) + float(t[7])) / 2.0).distance_to(here) > 40.0:
			continue
		tools_of[str(t[0])] = tools_of.get(str(t[0]), []) + [i]
	for g in tools_of.keys():
		var q := int(campus.queues.get(g, 0))
		if q > best_q:
			best_q = q
			best = g
	if best == "":
		return "I can't see a queue from here. Walk up to a bay and ask again."
	var down := 0
	var busy := 0
	for i in tools_of[best]:
		var m := str(campus.moods.get(i, ""))
		if m in ["hurt", "physio", "pm", "setup"]:
			down += 1
		elif m in ["work", "tired", "full"]:
			busy += 1
	var why := "its tools are all busy" if busy == tools_of[best].size() else ("%d of its %d tools here are down or in maintenance" % [down, tools_of[best].size()]) if down > 0 else "lots arrive in bursts"
	return "The longest queue near you is at %s: %d lots waiting. %s." % [best, best_q, why.capitalize()]


func _area_in(s: String) -> String:
	for a in campus.data["areas"].keys():
		var name := str(campus.data["areas"][a]["name"]).to_lower()
		if s.contains(name) or s.contains(str(a).to_lower().replace("_", " ")):
			return a
	var words := {"polish": "Planar", "cmp": "Planar", "litho": "Litho", "scanner": "Litho", "etch": "Dry_Etch",
			"furnace": "Diffusion", "implant": "Implant", "wet": "Wet_Etch", "clean": "Wet_Etch", "metal": "TF",
			"deposition": "Dielectric", "inspection": "Def_Met", "metrology": "TF_Met"}
	for k in words.keys():
		if s.contains(k):
			return words[k]
	return ""


func _label_of(area: String) -> Array:
	for l in campus.data["labels"]:
		if str(l[3]) == area:
			return l
	return []


func _on_lou(d: Dictionary) -> void:
	_lou_waiting = false
	guide.get_node("bubble").text = ""
	if d.get("fallback", false) or not d.get("ok", false):
		print("fab3d: lou fell back: ", d.get("message", d.get("error", d.get("errors", ""))))
		_rule_answer(_lou_q)
		return
	var say := str(d.get("say", ""))
	var tag := "Muse Spark Open  ·  %.1f s" % float(d.get("seconds", 0.0))
	print("fab3d: lou said ", JSON.stringify({"say": say, "walk_to": d.get("walk_to"), "explain": d.get("explain"),
			"try": d.get("try"), "tries": d.get("tries"), "seconds": d.get("seconds"), "cost_usd": d.get("cost_usd")}))
	if _lou_ask != "" and shots_dir != "":
		_shot_at.append(_t + 3.0)
		_shot_at.sort()
	var area = d.get("walk_to")
	var walking: bool = area is String and area != "" and _take_to(area, say, tag)
	if _lou_ask != "" and not walking:
		get_tree().create_timer(12.0).timeout.connect(func() -> void: get_tree().quit())
	if not walking:
		if guide.mode == "walk":
			# walking a tour leg: the answer goes on screen and the walk carries on
			ui.show_line(say)
			guide.get_node("bubble").text = tag
		else:
			guide.say(say, tag)
	var cards := []
	var tr = d.get("try_result")
	if tr is Dictionary:
		cards.append(_try_card(tr))
	var e = d.get("explain_entry")
	if e is Dictionary:
		cards.append("[b]%s[/b]\n%s\n\n%s" % [e.get("term", ""), e.get("plain", e.get("meaning", "")), e.get("here", "")])
	if not cards.is_empty():
		ui.show_card("\n\n".join(cards) + "\n\n[i]Lou's Meta brain: Muse Spark Open. Every number checked against the run.[/i]")


func _try_card(tr: Dictionary) -> String:
	if tr.has("error"):
		return "[b]What if[/b]\nThe simulator did not run: %s" % tr["error"]
	var b: Dictionary = tr.get("before", {})
	var a: Dictionary = tr.get("after", {})
	return ("[b]What if: %s[/b]\nat %s, on the same seed and day\n\nWafers a day: %s to %s\nLots waiting at %s at %s: %s to %s\n" +
			"Worst queue: %s (%s) to %s (%s)\n\n%s\n[i]%s[/i]") % [
			tr.get("what", ""), tr.get("group", ""), _num(b.get("wafers_per_day")), _num(a.get("wafers_per_day")),
			tr.get("group", ""), b.get("clock", ""), _num(b.get("group_waiting")), _num(a.get("group_waiting")),
			_num(b.get("worst_queue")), b.get("worst_group", ""), _num(a.get("worst_queue")), a.get("worst_group", ""),
			tr.get("line", ""), tr.get("about", "")]


func _num(v) -> String:
	if v == null:
		return "?"
	var f := float(v)
	return str(int(f)) if is_equal_approx(f, roundf(f)) else "%.1f" % f


func _near_area() -> String:
	# the area whose sign stands nearest the visitor, within 50 m, so Lou knows where "here" is
	var here := Vector2(player.global_position.x, -player.global_position.z)
	var best := ""
	var d := 50.0
	for l in campus.data["labels"]:
		var dd := Vector2(float(l[1]), float(l[2])).distance_to(here)
		if dd < d:
			d = dd
			best = str(l[3])
	return best


func _take_to(area: String, say: String, tag: String) -> bool:
	# Lou says the answer as he sets off and walks the visitor to the area's sign nearest them; off the clean floor (still
	# outside, or the walkable map not baked yet) both are placed there, as "show me" does
	var here := Vector2(player.global_position.x, -player.global_position.z)
	var l := []
	for c in campus.data["labels"]:
		if str(c[3]) == area and (l.is_empty() or Vector2(float(c[1]), float(c[2])).distance_to(here) <
				Vector2(float(l[1]), float(l[2])).distance_to(here)):
			l = c
	if l.is_empty():
		return false
	var z := float(campus.heights["clean_z"])
	var x := float(l[1])
	var side := 1.0 if float(l[2]) > 0 else -1.0
	var stop := {"kind": "lou", "area": area, "label": str(l[0]), "at": Vector3(x, z, -side * 5.0),
			"face": PI if side > 0 else 0.0, "plan": Vector2(x, float(l[2])),
			"device": _device_for(area, 0 if x < 261.8 else 1, Vector2(x, float(l[2])))}
	touring = false
	if not (guide.planning and absf(guide.global_position.y - z) < 0.6):
		guide.walk([])
		player.follow = null
		player.roaming = true
		player.place(x - 8.0, side * 2.0, -PI / 2)
		guide.global_position = Vector3(x - 3.0, z, -side * 5.0)
		guide.rotation.y = PI if side > 0 else 0.0
		guide.say(say + " " + _area_line(area, stop["plan"], str(l[0])), tag)
		return true
	var legs := []
	var from_p1 := guide.global_position.x < 261.8
	if from_p1 != (x < 261.8):
		# through the doorways in the phases' end walls and over the bridge
		var doors := [Vector3(255.0, z, 0.0), Vector3(316.0, z, 0.0)]
		if not from_p1:
			doors.reverse()
		for p in doors:
			legs.append({"kind": "via", "via": true, "at": p})
	legs.append(stop)
	if _lou_walk_was < 0.0:
		_lou_walk_was = guide.speed
	guide.speed = maxf(guide.speed, 4.0)      # a brisk walk: across a phase in under a minute
	guide.walk(legs)
	guide.get_node("bubble").text = tag
	ui.show_line(say)
	ui.set_stop(0, 0, "Lou takes you to " + str(l[0]))
	player.roaming = false
	player.follow = guide
	return true


func _on_answer(d: Dictionary) -> void:
	var text := str(d.get("answer", "")) if d.get("answer") != null else str(d.get("message", d.get("error", "")))
	guide.say(text if text != "" else "I don't know that one yet.")


func _on_heard(d: Dictionary) -> void:
	if d.has("text") and str(d["text"]).strip_edges() != "":
		handle_question(str(d["text"]))
	else:
		ui.show_line(str(d.get("error", "I didn't catch that.")))


func _unhandled_input(e: InputEvent) -> void:
	if not cues.is_empty() and e is InputEventKey and e.pressed and not e.echo \
			and (e.keycode == KEY_BRACKETRIGHT or e.keycode == KEY_BRACKETLEFT):
		# Lou's next (or last) line for the video, typed out in his own window
		cue_i = clampi(cue_i + (1 if e.keycode == KEY_BRACKETRIGHT else -1), 0, cues.size() - 1)
		ui.show_line(str(cues[cue_i]["text"]))
		get_viewport().set_input_as_handled()
		return
	if e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT:
		var cam: Camera3D = player.camera
		var i: int = campus.tool_at(cam.project_ray_origin(e.position), cam.project_ray_normal(e.position))
		if i < 0:
			ui.show_card("")
			return
		var t: Array = campus.data["tools"][i]
		var st: Dictionary = campus.stage_of(str(t[1]))
		var mood := str(campus.moods.get(i, "not reported yet"))
		ui.show_card("[b]%s[/b]  ·  %s\n%s, phase %d\nState: [b]%s[/b]   ·   lots waiting for the group: %d\n\n%s" % [
				t[0], str(t[2]).replace("_", " "), campus.area_name(str(t[1])), int(t[3]) + 1, mood,
				int(campus.queues.get(str(t[0]), 0)), str(st.get("what", ""))])


# ------------------------------------------------------------------ the frame-rate bar (docs/FAB-3D.md, F8)

func _write_perf() -> void:
	var a := _frame_ms.duplicate()
	a.sort()
	var n := a.size()
	var drawn := Engine.get_frames_drawn() - _drawn0
	var size := get_viewport().get_visible_rect().size
	var slow := []          # [second into the timed run, ms] for each frame over a 60 Hz frame
	var at := 0.0
	for ms in _frame_ms:
		at += ms / 1000.0
		if ms > 17.5:
			slow.append([snappedf(at, 0.01), snappedf(ms, 0.1)])
	var report := {"frames": n, "median_ms": a[n / 2], "p99_ms": a[int(n * 0.99)], "worst_ms": a[n - 1], "slow": slow,
			"drawn_share": float(drawn) / float(n), "width": int(size.x), "height": int(size.y),
			"renderer": RenderingServer.get_current_rendering_method(), "device": RenderingServer.get_video_adapter_name(),
			"about": "The guide's tour, timed on this machine. From the SMT2020 testbed; not a real fab."}
	var f := FileAccess.open(perf_out, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	get_tree().quit()


# ------------------------------------------------------------------ the headless check (docs/FAB-3D.md, F6)

func _check() -> void:
	await get_tree().process_frame
	# the cinema: a visitor in the hall does not start the film; floors follow the built model
	player.place(51.7, -115.0, PI / 2.0)
	await get_tree().process_frame
	await get_tree().process_frame
	var cin := {"seats": cinema.seats.size(), "people": cinema.people.size(), "posters": cinema.posters,
			"film_started_by_walking_in": cinema.started, "floor_map": not player.cin_floor.is_empty(),
			"floor_mid_aisle": player.floor_at(51.7, -115.0), "floor_row5": player.floor_at(54.55, -116.0),
			"floor_stair_top": player.floor_at(59.5, -116.2), "floor_projection": player.floor_at(60.0, -113.0),
			"floor_ramp_top": player.floor_at(51.5, -109.1)}
	# every doorway is open (a ray across it at chest height hits nothing); walking south through the ramp door ends
	# in the hall, and the same walk 2.8 m west is stopped by the wall
	await get_tree().physics_frame
	await get_tree().physics_frame
	var space := get_world_3d().direct_space_state
	var shut := []
	for dr in cinema.doors:
		if dr[1] != "swing":
			continue
		var c: Vector3 = dr[2] + Vector3(0, 0.3, 0)
		var across := Vector3(0, 0, 0.6) if str(dr[4]["along"]) == "x" else Vector3(0.6, 0, 0)
		if not space.intersect_ray(PhysicsRayQueryParameters3D.create(c - across, c + across)).is_empty():
			shut.append(str(dr[4]["name"]))
	if not nav_ready:
		await nav_baked
	var blocked := []
	var planned := 0
	var route := _tour()
	var prev: Vector3 = route[0]["at"]
	for k in range(1, route.size()):
		var st: Dictionary = route[k]
		var to: Vector3 = st["at"]
		if st.get("via", false) and not (st.get("bump", false) or st.get("ride", false)):
			to = reach(prev, to)
		if not (st.get("teleport", false) or st.get("bump", false) or st.get("ride", false) or str(st["kind"]) == "air_shower"):
			var pts := [prev] + _plan_leg(prev, to) + [to]
			planned += 1 if pts.size() > 2 else 0
			for m in range(1, pts.size()):
				var hit := leg_hit(pts[m - 1], pts[m])
				if hit != "":
					blocked.append("%d %s: %s" % [k, str(st["kind"]), hit])
					break
		prev = to
	cin["guide_legs_planned"] = planned
	cin["guide_legs_blocked"] = blocked
	cin["guide_legs"] = route.size() - 1
	cin["doorways"] = cinema.doors.size()
	cin["doorways_blocked"] = shut
	for spot in [[52.31, "through_ramp_door"], [49.5, "walked_into_wall"]]:
		player.place(float(spot[0]), -109.3, PI)
		for k in 60:
			player.move(Vector3(0, 0, 0.05))
		cin[spot[1]] = cinema.in_hall(player.global_position)
	cinema.sit("R5C4")
	await get_tree().process_frame
	await get_tree().process_frame
	cin["seated"] = player.seated
	cin["seated_eye_over_floor"] = player.global_position.y - player.floor_at(player.global_position.x, -player.global_position.z)
	cinema.play()
	cinema.fullscreen(true)
	cin["fullscreen"] = cinema.full.visible
	var movie := {"world_locked_during_movie": player.input_locked, "world_draw_suspended": get_viewport().disable_3d}
	var movie_key := InputEventKey.new()
	movie_key.pressed = true
	movie_key.keycode = KEY_SPACE
	cinema._input(movie_key)
	movie["paused"] = cinema.video.paused and cinema.user_paused
	cinema._input(movie_key)
	movie["resumed"] = not cinema.video.paused and not cinema.user_paused
	movie_key.keycode = KEY_ESCAPE
	cinema._input(movie_key)
	movie["returned_to_hall"] = not cinema.full.visible and player.seated
	movie["world_locked_after_movie"] = player.input_locked
	movie["world_draw_restored"] = not get_viewport().disable_3d
	cinema.fullscreen(true)
	movie_key.keycode = KEY_E
	cinema._input(movie_key)
	movie["stood_from_fullscreen"] = not player.seated and not cinema.full.visible and not get_viewport().disable_3d
	cinema.sit("R5C4")
	cinema.user_paused = true
	cinema._on_finished()
	movie["replay_keeps_old_pause"] = cinema.user_paused
	var saved_stream = cinema.video.stream
	cinema.video.stop()
	cinema.video.stream = null
	cinema.fullscreen(true)
	movie["missing_movie_stays_in_hall"] = not cinema.full.visible
	cinema.video.stream = saved_stream
	cinema.stand()
	var seat: Array = cinema.seats["R5C4"]
	var polish := {"still_seated": player.seated,
		"stand_error": Vector2(player.position.x - (seat[0] - 0.6), -player.position.z - seat[1]).length(),
		"seat_outside_hall": cinema.nearest_free(Vector3(0, 1.75, 0)),
		"seat_wrong_level": cinema.nearest_free(Vector3(seat[0] - 0.6, 20, -seat[1])),
		"ground_entry": player.floor_at(-5.8, 31.3, 1.75),
		"upper_entry": player.floor_at(-1.7, 31.3, 9.15),
		"cleanroom": player.floor_at(10.0, 0.0, 1.75)}
	ui.ask_panel.show()
	ui.ask_box.grab_focus()
	var key := InputEventKey.new()
	key.keycode = KEY_F
	key.pressed = true
	player._unhandled_input(key)
	polish["typing_toggled_flight"] = player.fly
	ui.ask_box.release_focus()
	ui.ask_panel.hide()
	player.place(285.0, 0.0, -PI / 2)
	campus.update_cells(true)
	var v := Vector2(285.0, 0.0)
	var far := 0.0
	for cid in campus.loaded.keys():
		far = max(far, campus.cell_centre(cid).distance_to(v))
	var scenes := []
	for pair in [["stocker", "res://tools/stocker.tscn"], ["carrier_standard", "res://carriers/standard.tscn"],
			["carrier_copper", "res://carriers/copper.tscn"], ["guide", "res://guide/ceo.tscn"], ["cinema", "res://cinema/cinema.tscn"]]:
		if ResourceLoader.exists(pair[1]):
			scenes.append(pair[0])
	var kinds := []
	for k in campus.kinds.keys():
		if k != "stocker":
			kinds.append(k)
	var device_shots := []
	for stop in _tour():
		if stop.get("kind") != "area":
			continue
		var shot: Dictionary = stop["device"]
		var t: Array = campus.data["tools"][shot["tool"]]
		var target: Vector3 = shot["target"]
		device_shots.append({"area": stop["area"], "tool_area": t[1],
			"phase": 0 if stop["at"].x < 261.8 else 1, "tool_phase": t[3],
			"same_side": signf(-target.z) == signf(stop["plan"].y),
			"distance": Vector2(target.x, target.z).distance_to(Vector2(stop["at"].x, stop["at"].z))})
	var report := {"device_shots": device_shots, "opened": true, "polish": polish, "movie": movie, "kinds": kinds, "scenes": scenes, "viewer_at": "bridge", "cinema": cin,
			"cells_loaded": campus.loaded.size(), "cells_full": campus.full_ids.size(), "tools_built": campus.tool_nodes.size(),
			"farthest_loaded_m": far, "cells_total": campus.data["cells"].size(), "cinema_film": cinema.film_path(), "cinema_films": cinema.titles,
			"drone": {"scene": ResourceLoader.exists("res://drone/drone.tscn"), "keys": drone.keys.size(),
				"seconds": drone.length()},
			"entrance": {"scene": entrance != null and ResourceLoader.exists("res://entrance/entrance.tscn"),
				"lift_car": entrance.car != null}, "tour_first": str(_tour()[0]["kind"]),
			"about": "From the SMT2020 testbed; a gigafab-style layout of our own design; not a real fab."}
	var f := FileAccess.open(check_out, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	get_tree().quit()


func _plain(c: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	return m

