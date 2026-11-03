extends Node3D
## The 3D fab and its guide (docs/FAB-3D.md): the campus streamed around the visitor, the simulator running live in the
## helper, the robot CEO's tour through both phases to the cinema, then free exploration. Questions are answered from
## the live run by plain rules first; anything else goes to the helper (Meta's model, through the glossary). From the
## SMT2020 testbed; a gigafab-style layout of our own design; not a real fab.

const Looks := preload("res://looks.gd")
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


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if "--check" in args:
		check_out = args[args.find("--check") + 1]
	if "--perf" in args:
		perf_out = args[args.find("--perf") + 1]
	if "--film" in args:
		film = true
	if "--shots" in args:
		shots_dir = args[args.find("--shots") + 1]
	near_vehicle = "--near-vehicle" in args
	no_intro = "--no-intro" in args or near_vehicle
	sweep = "--sweep" in args
	corridor = "--corridor" in args
	if "--no-ssao" in args:
		$environment.environment.ssao_enabled = false
	if "--taa" in args:
		get_viewport().use_taa = true
	soft_facade = "--soft-facade" in args
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
	player.setup(campus.data)
	guide.line_of = Callable(self, "_line_for")
	guide.said.connect(func(t: String) -> void: ui.show_line(t))
	guide.arrived.connect(_on_arrived)
	guide.tour_done.connect(_free_walk)
	live.run_ready.connect(_on_run)
	live.state.connect(_on_state)
	live.answered.connect(_on_answer)
	live.heard.connect(_on_heard)
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


func _after_intro() -> void:
	intro = false
	campus.paused = false
	_start_tour()


func _start_tour() -> void:
	ui.show_line("The run is ready: %d tools, the simulator's day from 06:00. Follow me." % campus.data["tools"].size())
	touring = true
	_stop_n = 0
	_stop_total = 0
	for st in _tour():
		if not st.get("via", false) and not st.get("ride", false):
			_stop_total += 1
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
	guide.start(tour)


func _process(dt: float) -> void:
	_t += dt
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
	ui.talking = intro or (touring and guide.mode == "talk")
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
					"face": PI if side > 0 else 0.0, "plan": Vector2(x, float(l[2]))})
		if phase == 0:
			# through the doorway in phase one's end wall, onto the bridge, and through phase two's
			stops.append({"kind": "via", "via": true, "at": Vector3(255.0, z, 0.0)})
			stops.append({"kind": "bridge", "at": Vector3(285.8, z, 0.0), "face": -PI / 2})
			stops.append({"kind": "via", "via": true, "at": Vector3(316.0, z, 0.0)})
	# the cinema (data/cinema/plan.json): in by the main entrance, across the lobby, up the ramp, onto the mid cross aisle
	stops.append({"kind": "cinema_door", "at": Vector3(58.0, 0.1, 92.0), "face": PI, "teleport": true})
	for p in [[58.0, -99.5, 0.1], [69.2, -104.5, 0.1], [69.2, -109.1, 0.1], [61.2, -109.1, 0.7], [59.7, -109.1, 0.7],
			[52.5, -109.1, 1.3], [52.3, -109.1, 1.3]]:
		stops.append({"kind": "via", "via": true, "at": Vector3(p[0], p[2], -p[1])})
	stops.append({"kind": "cinema", "at": Vector3(52.3, 1.3, 112.0), "face": PI / 2.0})
	return stops


func _on_arrived(s: Dictionary) -> void:
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
	if film and s["kind"] == "cinema":
		get_tree().create_timer(14.0).timeout.connect(func() -> void: get_tree().quit())
	if s.get("teleport", false):
		player.global_position = s["at"] + Vector3(0, 2.6, -4.5)
	if s["kind"] == "cinema":
		player.follow = null
		player.roaming = true
		# the view from a seat in row 5 (data/cinema/plan.json: floor 1.8 m, eyes 1.15 m above it), at the screen
		player.global_position = Vector3(54.4, player.floor_at(54.4, -116.0) + 1.15, 116.0)
		player.yaw = PI / 2.0
		player.pitch = -0.04


func _stop_title(s: Dictionary) -> String:
	match str(s["kind"]):
		"lot": return "The parking lot"
		"pavilion": return "Visitors' entrance"
		"lift": return "The lift"
		"gowning": return "Gowning room"
		"air_shower": return "Air shower"
		"cleanroom": return "The cleanroom"
		"area": return str(s.get("label", ""))
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
		"area":
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
			return "Take a seat. The film starts when you're in the hall. Afterwards, walk anywhere: click a tool for its card, or ask me anything."
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
	var s := q.to_lower()
	ui.show_line("[i]You asked:[/i] %s" % q)
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


func _on_answer(d: Dictionary) -> void:
	var text := str(d.get("answer", "")) if d.get("answer") != null else str(d.get("message", d.get("error", "")))
	guide.say(text if text != "" else "I don't know that one yet.")


func _on_heard(d: Dictionary) -> void:
	if d.has("text") and str(d["text"]).strip_edges() != "":
		handle_question(str(d["text"]))
	else:
		ui.show_line(str(d.get("error", "I didn't catch that.")))


func _unhandled_input(e: InputEvent) -> void:
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
	var report := {"opened": true, "kinds": kinds, "scenes": scenes, "viewer_at": "bridge",
			"cells_loaded": campus.loaded.size(), "cells_full": campus.full_ids.size(), "tools_built": campus.tool_nodes.size(),
			"farthest_loaded_m": far, "cells_total": campus.data["cells"].size(), "cinema_film": cinema.film_path(),
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

