extends Node3D
## The 3D fab and its guide (docs/FAB-3D.md): the campus streamed around the visitor, the simulator running live in the
## helper, the robot CEO's tour through both phases to the cinema, then free exploration. Questions are answered from
## the live run by plain rules first; anything else goes to the helper (Meta's model, through the glossary). From the
## SMT2020 testbed; a gigafab-style layout of our own design; not a real fab.

@onready var campus: Node3D = $campus
@onready var live: Node = $live
@onready var player: Node3D = $player
@onready var guide: Node3D = $guide
@onready var cinema: Node3D = $cinema
@onready var ui: CanvasLayer = $ui
@onready var building: Node3D = $building

var clock := 360.0            # simulated minutes since the run began: 06:00 on day 1
var speed := 1.0              # simulated minutes a real second
var _ask_every := 0.0
var staff_scene: PackedScene = preload("res://staff/staff.tscn")
var staff := {}               # tool index -> worker
var check_out := ""
var perf_out := ""
var shots_dir := ""
var touring := false
var _t := 0.0
var _frame_ms: PackedFloat32Array = PackedFloat32Array()
var _drawn0 := 0
var _shot_at := [6.0, 14.0, 24.0, 34.0, 46.0]


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if "--check" in args:
		check_out = args[args.find("--check") + 1]
	if "--perf" in args:
		perf_out = args[args.find("--perf") + 1]
	if "--shots" in args:
		shots_dir = args[args.find("--shots") + 1]
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
	_dress_building()
	player.place(6.0, 0.0, -PI / 2)
	guide.global_position = Vector3(12.0, float(campus.heights["clean_z"]), 0.0)
	guide.rotation.y = -PI / 2
	print("fab3d: ready; shots=", shots_dir, " perf=", perf_out, " check=", check_out)
	if check_out != "":
		_check.call_deferred()
		return
	live.start(1, 1.0)


func _dress_building() -> void:
	var looks := {"flooring": [Color(0.58, 0.6, 0.62), 0.55], "slab_floor": [Color(0.5, 0.52, 0.55), 0.7],
			"column": [Color(0.72, 0.73, 0.72), 0.6], "wall": [Color(0.8, 0.81, 0.8), 0.7],
			"ceiling": [Color(0.86, 0.88, 0.9), 0.4], "roof": [Color(0.45, 0.47, 0.5), 0.8]}
	for mi in building.find_children("*", "MeshInstance3D", true, false):
		for k in looks.keys():
			if str(mi.name).contains(k):
				var m := StandardMaterial3D.new()
				m.albedo_color = looks[k][0]
				m.roughness = looks[k][1]
				if k == "ceiling":
					m.emission_enabled = true
					m.emission = Color(0.95, 0.97, 1.0)
					m.emission_energy_multiplier = 0.35
				mi.material_override = m


# ------------------------------------------------------------------ the run and the clock

func _on_run(info: Dictionary) -> void:
	ui.show_line("The run is ready: %d tools, the simulator's day from 06:00. Follow me." % campus.data["tools"].size())
	touring = true
	player.roaming = false
	player.follow = guide
	guide.start(_tour())


func _process(dt: float) -> void:
	_t += dt
	if shots_dir != "" and not _shot_at.is_empty() and _t >= _shot_at[0]:
		_shot_at.pop_front()
		var path := "%s/shot-%02d.png" % [shots_dir, int(_t)]
		var err := get_viewport().get_texture().get_image().save_png(path)
		print("shot ", path, " ", err, " cells ", campus.loaded.size(), " tools ", campus.tool_nodes.size(), " run ", live.run_id)
		if _shot_at.is_empty():
			get_tree().quit()
	if perf_out != "" and live.run_id != "":
		if _frame_ms.is_empty():
			_drawn0 = Engine.get_frames_drawn()
		_frame_ms.append(dt * 1000.0)
		if _frame_ms.size() >= 3600:
			_write_perf()
	if live.run_id != "":
		clock += dt * speed
		campus.clock = clock
		ui.set_clock(clock, speed)
		_ask_every -= dt
		if _ask_every <= 0.0:
			_ask_every = 1.0
			live.ask_state(clock, campus.full_ids, max(2.0, speed * 2.0))
	# lift the roof and the filter ceiling away when the visitor flies above them
	var above := player.global_position.y > 17.0
	for c in building.find_children("*roof*", "", true, false) + building.find_children("*ceiling*", "", true, false):
		c.visible = not above


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
		var front := tool.global_transform.basis.z.normalized()
		var t: Array = campus.data["tools"][i]
		var reach := maxf(float(t[5]) - float(t[4]), float(t[7]) - float(t[6])) / 2.0
		w.global_position = tool.global_position + front * (reach + 0.9)
		w.rotation.y = tool.rotation.y + PI
		w.dress(want[i][0], want[i][1])
		staff[i] = w


# ------------------------------------------------------------------ the tour

func _tour() -> Array:
	var z := float(campus.heights["clean_z"])
	var stops: Array = []
	var seen := {}
	var labels: Array = campus.data["labels"].duplicate()
	labels.sort_custom(func(a, b) -> bool: return float(a[1]) < float(b[1]))
	for phase in [0, 1]:
		for l in labels:
			var x := float(l[1])
			var in_p1 := x < 261.8
			if (phase == 0) != in_p1 or seen.has([phase, str(l[3])]):
				continue
			seen[[phase, str(l[3])]] = true
			var side := 1.0 if float(l[2]) > 0 else -1.0
			stops.append({"kind": "area", "area": str(l[3]), "label": str(l[0]), "at": Vector3(x, z, -side * 5.0),
					"face": PI if side > 0 else 0.0, "plan": Vector2(x, float(l[2]))})
		if phase == 0:
			stops.append({"kind": "bridge", "at": Vector3(285.0, z, 0.0), "face": -PI / 2})
	stops.append({"kind": "cinema_door", "at": Vector3(58.0, 0.1, 90.0), "face": PI, "teleport": true})
	stops.append({"kind": "cinema", "at": Vector3(58.0, 0.1, 106.5), "face": 0.0})
	return stops


func _on_arrived(s: Dictionary) -> void:
	if s.get("teleport", false):
		player.global_position = s["at"] + Vector3(0, 2.6, -4.5)
	if s["kind"] == "cinema":
		player.follow = null
		player.roaming = true
		player.place(58.0, -110.0, PI)


func _free_walk() -> void:
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
	var report := {"frames": n, "median_ms": a[n / 2], "p99_ms": a[int(n * 0.99)], "worst_ms": a[n - 1],
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
			"about": "From the SMT2020 testbed; a gigafab-style layout of our own design; not a real fab."}
	var f := FileAccess.open(check_out, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	get_tree().quit()
