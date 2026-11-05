extends Node3D
## The campus cinema (docs/FAB-3D.md): the silicon film, "From sand to chip", on the hall's screen. The visitor walks to
## a free seat and presses E to sit; seated, Enter plays the film full screen (Esc back to the hall, Space pauses). The
## film pauses when the visitor leaves the hall. A few people sit in the hall already. The film is ours, converted to
## Ogg Theora (the video format Godot plays); seats and floors come from the rules-made plan (data/cinema/plan.json)
## through Blender (data/cinema-built.json). From the SMT2020 testbed; not a real fab.

signal prompt(text: String)

const FILM := "res://data/film/from-sand-to-chip.ogv"   # the first film, if the new ones are not prepared
# what the hall shows, picked at the seat with 1 and 2: [title on the screen, Theora file]
const FILMS := [["SAND TO CHIP", "res://data/film/sand-to-chip-v10.ogv"],
		["CRIME && PUNISHMENT", "res://data/film/crime-and-punishment-acted.ogv"]]
const HALL := Rect2(40.3, -121.7, 17.7, 11.4)     # plan x, y, depth, width of the hall (data/cinema/plan.json)
const REACH := 0.6                                # metres from the spot in front of a seat at which the visitor can sit
const EYE := 1.15                                 # seated eye height over the tier (the plan's choice)
# who is in already (made up): plan seat id and a jumper colour
const PEOPLE := [["R1C6", Color(0.16, 0.22, 0.4)], ["R1C7", Color(0.55, 0.42, 0.2)], ["R6N3", Color(0.42, 0.12, 0.16)],
		["R2S2", Color(0.15, 0.4, 0.38)]]
const POSTERS := [
	["Sand to Chip", preload("res://cinema/posters/sand-to-chip.jpg")],
	["Crime && Punishment", preload("res://cinema/posters/crime-and-punishment.jpg")],
	["Cache Me If You Can", preload("res://cinema/posters/cache-me-if-you-can.webp")],
	["Wafer Thin", preload("res://cinema/posters/wafer-thin.webp")],
]
const Looks := preload("res://looks.gd")
const FONT := preload("res://ui/fonts/kenpixel.ttf")

var viewer: Node3D
var guide: Node3D                 # Lou; doors open for him too
var doors := []                   # [pivot or [left, right], kind, centre (Vector3), open amount 0..1, data]
const DOOR_NEAR := 2.6            # metres at which a door starts to open for someone
const DOOR_RATE := 1.6            # of its full swing a second
var autoplay := false             # the recorded film starts it on its own; a visitor presses Enter
var seats := {}                   # plan seat id -> [x, y, level]
var taken := {}
var people := []
var posters := 0
var started := false
var user_paused := false
var _seat_id := ""
var _near := ""
var _said := "-"
var _hint_seconds := 0.0
var film := 0                     # which of FILMS is on the screen
var titles := []                  # the titles of the films this build holds
var captions: Array = []
var staff_scene: PackedScene = preload("res://staff/staff.tscn")
@onready var vp: SubViewport = $vp
@onready var video: VideoStreamPlayer = $vp/video
@onready var card: Control = $vp/card
@onready var subtitle: Label = $vp/subtitle
@onready var full: CanvasLayer = $full
@onready var picture: TextureRect = $full/picture
@onready var full_hint: Label = $full/hint


func _ready() -> void:
	var lobby: StandardMaterial3D = Looks.pbr("brushed_concrete", 2.5, Color(0.72, 0.69, 0.63), 0.0, "diff", true).duplicate()
	lobby.albedo_texture = null
	lobby.normal_scale = 0.12
	lobby.roughness = 0.7
	Looks.dress($model, {
		"cinema_lobby_floor": lobby,
		"cinema_paving": Looks.pbr("concrete_pavement", 2.5, Color.WHITE, 0.0, "diff", true)})
	for f in FILMS:
		if ResourceLoader.exists(f[1]):
			titles.append(f[0])
	if titles.is_empty() and ResourceLoader.exists(FILM):
		video.stream = load(FILM)
	else:
		pick(0)
	video.finished.connect(_on_finished)
	var screen := _find(self, "screen")
	if screen:
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.albedo_texture = vp.get_texture()
		screen.material_override = m
	picture.texture = vp.get_texture()
	full.visible = false
	# the building is solid: walls, rails, seat backs and the screen stop the visitor and the camera
	for mi in _meshes($model):
		mi.create_trimesh_collision()


static func w(x: float, y: float, z: float) -> Vector3:
	return Vector3(x, z, -y)


func setup(data: Dictionary) -> void:
	for s in data.get("seats", []):
		seats[str(s[0])] = [float(s[1]), float(s[2]), float(s[3])]
	for p in PEOPLE:
		if seats.has(p[0]):
			_seat_person(str(p[0]), p[1])
	var path := "res://data/cinema-built.json"
	if FileAccess.file_exists(path):
		var built = JSON.parse_string(FileAccess.get_file_as_string(path))
		if built is Dictionary:
			var k := 0
			for p in built.get("posters", []):
				_poster(p, k % POSTERS.size())
				k += 1
			posters = k
			for d in built.get("doors", []):
				_door(d)
			if built.has("entrance"):
				_sliding(built["entrance"])


func _seat_person(id: String, jumper: Color) -> void:
	var s: Array = seats[id]
	var who: Node3D = staff_scene.instantiate()
	add_child(who)
	who.position = w(s[0] - 0.12, s[1], 0.04 + s[2])
	who.rotation.y = -PI / 2.0                     # facing the screen on the west wall
	who.dress("operator", "Sitting_Idle_Loop")
	# out of the cleanroom: no goggles or mask, a jumper in place of the suit
	var mi := _mesh_of(who)
	if mi:
		var hide := StandardMaterial3D.new()
		hide.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		hide.albedo_color = Color(0, 0, 0, 0)
		var top := StandardMaterial3D.new()
		top.albedo_color = jumper
		top.roughness = 0.9
		var shoe := StandardMaterial3D.new()
		shoe.albedo_color = Color(0.12, 0.11, 0.1)
		for k in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(k)
			var n := m.resource_name if m else ""
			if n in ["staff_goggle", "staff_frame", "staff_mask", "staff_tape"]:
				mi.set_surface_override_material(k, hide)
			elif n in ["staff_suit", "staff_fold", "staff_trim"]:
				mi.set_surface_override_material(k, top)
			elif n in ["staff_boot", "staff_sole"]:
				mi.set_surface_override_material(k, shoe)
	taken[id] = true
	people.append(id)


func _meshes(n: Node) -> Array:
	var out := []
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		out += _meshes(c)
	return out


func _door(d: Dictionary) -> void:
	# one leaf hung on the jamb at the low end of its opening, swinging out of the hall (the way people leave)
	var at: Array = d["at"]
	var wdt := float(d["clear_m"])
	var hgt := float(d["height"])
	var along_x := str(d["along"]) == "x"
	var hinge := w(float(at[0]) - wdt / 2.0, float(at[1]), float(d["z"])) if along_x else w(float(at[0]), float(at[1]) - wdt / 2.0, float(d["z"]))
	var pivot := Node3D.new()
	pivot.position = hinge
	add_child(pivot)
	var leaf := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(wdt, hgt, 0.05) if along_x else Vector3(0.05, hgt, wdt)
	leaf.mesh = bm
	leaf.position = Vector3(wdt / 2.0, hgt / 2.0, 0.0) if along_x else Vector3(0.0, hgt / 2.0, -wdt / 2.0)
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.36, 0.2, 0.14)
	m.roughness = 0.6
	leaf.material_override = m
	pivot.add_child(leaf)
	doors.append([pivot, "swing", w(float(at[0]), float(at[1]), float(d["z"]) + 1.0), 0.0, d])


func _sliding(e: Dictionary) -> void:
	# the main entrance: two glass leaves that slide apart behind the fixed glass
	var half := (float(e["x1"]) - float(e["x0"])) / 2.0
	var g := StandardMaterial3D.new()
	g.albedo_color = Color(0.55, 0.75, 0.88, 0.3)
	g.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	g.roughness = 0.05
	var leaves := []
	for side in [-1.0, 1.0]:
		var leaf := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(half, float(e["z1"]) - float(e["z0"]), 0.03)
		leaf.mesh = bm
		leaf.material_override = g
		add_child(leaf)
		leaves.append([leaf, side])
	var cx := (float(e["x0"]) + float(e["x1"])) / 2.0
	doors.append([leaves, "slide", w(cx, float(e["y"]), 1.0), 0.0, e])


func _doors(dt: float) -> void:
	for dr in doors:
		var near := false
		for who in [viewer, guide]:
			if who and Vector2(who.global_position.x - dr[2].x, who.global_position.z - dr[2].z).length() < DOOR_NEAR \
					and absf(who.global_position.y - dr[2].y) < 2.5:
				near = true
		dr[3] = clampf(dr[3] + (DOOR_RATE if near else -DOOR_RATE) * dt, 0.0, 1.0)
		var u := smoothstep(0.0, 1.0, dr[3])
		if dr[1] == "swing":
			var along_x := str(dr[4]["along"]) == "x"
			var out: Array = dr[4]["out"]
			# along x the leaf points +x from its hinge: north (out +y, Godot -z) is a turn of +90 deg, south -90;
			# along y it points Godot -z (plan +y) from its hinge: east (out +x) is a turn of -90 deg
			var turn := (PI / 2.0 if float(out[1]) > 0.0 else -PI / 2.0) if along_x else -PI / 2.0
			dr[0].rotation.y = turn * u
		else:
			var e: Dictionary = dr[4]
			var half := (float(e["x1"]) - float(e["x0"])) / 2.0
			var cx := (float(e["x0"]) + float(e["x1"])) / 2.0
			for lv in dr[0]:
				var side: float = lv[1]
				lv[0].position = w(cx + side * (half / 2.0 + half * 0.95 * u), float(e["y"]) + 0.08, (float(e["z0"]) + float(e["z1"])) / 2.0)


func _poster(p: Dictionary, index: int) -> void:
	# Keep the entire poster inside the existing lightbox, even for a future
	# artwork with a different aspect ratio. No crop and no overlaid title.
	var texture: Texture2D = POSTERS[index][1]
	var width := float(p["x1"]) - float(p["x0"])
	var height := float(p["z1"]) - float(p["z0"])
	var frame := MeshInstance3D.new()
	frame.name = "Poster%d" % index
	frame.set_meta("title", POSTERS[index][0])
	var backing := QuadMesh.new()
	backing.size = Vector2(width, height)
	frame.mesh = backing
	var black := StandardMaterial3D.new()
	black.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	black.albedo_color = Color(0.015, 0.018, 0.025)
	frame.material_override = black
	frame.position = w((float(p["x0"]) + float(p["x1"])) / 2.0, float(p["y"]) + 0.015, (float(p["z0"]) + float(p["z1"])) / 2.0)
	frame.rotation.y = PI                         # front faces north into the lobby
	add_child(frame)
	var art := MeshInstance3D.new()
	art.name = "Artwork"
	var quad := QuadMesh.new()
	var fit := minf((width - 0.04) / texture.get_width(), (height - 0.06) / texture.get_height())
	quad.size = texture.get_size() * fit
	art.mesh = quad
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_texture = texture
	material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	art.material_override = material
	art.position.z = 0.003
	frame.add_child(art)


func pick(i: int) -> void:
	# a seated visitor picks a film: it starts again from the top
	var have := FILMS.filter(func(f): return ResourceLoader.exists(f[1]))
	if i < 0 or i >= have.size():
		return
	film = i
	video.stop()
	video.stream = load(have[i][1])
	captions.clear()
	var metadata := str(have[i][1]).get_basename() + ".film.json"
	if FileAccess.file_exists(metadata):
		var data = JSON.parse_string(FileAccess.get_file_as_string(metadata))
		if data is Dictionary:
			captions = data.get("captions", [])
	subtitle.text = ""
	started = false
	user_paused = false
	if card:
		card.visible = true
		$vp/card/lines/now.text = "NOW SHOWING"
		$vp/card/lines/title.text = have[i][0]
		$vp/card/lines/how.text = "TAKE A SEAT, THEN PRESS ENTER"


func film_path() -> String:
	return video.stream.resource_path if video and video.stream else ""


func _find(n: Node, name: String) -> MeshInstance3D:
	if n is MeshInstance3D and n.name.begins_with(name):
		return n
	for c in n.get_children():
		var m := _find(c, name)
		if m:
			return m
	return null


func _mesh_of(n: Node) -> MeshInstance3D:
	if n is MeshInstance3D:
		return n
	for c in n.get_children():
		var m := _mesh_of(c)
		if m:
			return m
	return null


func in_hall(p: Vector3) -> bool:
	return HALL.has_point(Vector2(p.x, -p.z))


func seat_label(id: String) -> String:
	# R5C4 -> ROW 5, SEAT C4
	var c := 1
	while c < id.length() and id[c] >= "0" and id[c] <= "9":
		c += 1
	return "ROW %s, SEAT %s" % [id.substr(1, c - 1), id.substr(c)]


func nearest_free(p: Vector3) -> String:
	var best := ""
	if not in_hall(p):
		return best
	var bd := REACH
	for id in seats:
		if taken.has(id):
			continue
		var s: Array = seats[id]
		if absf(p.y - (0.04 + s[2] + 1.65)) > 0.65:
			continue
		# measured from where you stand to sit in it: just in front of its seat pan
		var d := Vector2(p.x - (s[0] - 0.6), -p.z - s[1]).length()
		if d < bd:
			bd = d
			best = id
	return best


func sit(id: String) -> void:
	if not seats.has(id) or taken.has(id):
		return
	_seat_id = id
	var s: Array = seats[id]
	viewer.sit(w(s[0] - 0.12, s[1], 0.04 + s[2] + EYE), PI / 2.0)
	_near = id


func stand() -> void:
	viewer.stand()
	if seats.has(_seat_id):
		var s: Array = seats[_seat_id]
		viewer.place(s[0] - 0.6, s[1], PI / 2.0)
	_seat_id = ""
	fullscreen(false)


func play() -> void:
	if not video.stream:
		card.visible = true
		$vp/card/lines/now.text = "FILM UNAVAILABLE"
		$vp/card/lines/how.text = "RETURN TO THE HALL WITH ESC"
		return
	if not started:
		video.play()
		started = true
	user_paused = false
	video.paused = false
	card.visible = false


func fullscreen(on: bool) -> void:
	if on and not video.stream:
		return
	if on:
		viewer.release_look()
	full.visible = on
	# The opaque movie covers the world; skip its 3D draw until returning to the hall.
	get_viewport().disable_3d = on
	viewer.input_locked = on
	Input.mouse_mode = Input.MOUSE_MODE_HIDDEN if on else Input.MOUSE_MODE_VISIBLE
	_hint_seconds = 4.0
	full_hint.modulate.a = 1.0


func _on_finished() -> void:
	started = false
	user_paused = false
	subtitle.text = ""
	fullscreen(false)
	card.visible = true
	$vp/card/lines/now.text = "THE END"
	$vp/card/lines/how.text = "PRESS ENTER TO WATCH AGAIN"


func _input(e: InputEvent) -> void:
	if not viewer or not e.is_pressed() or e.is_echo():
		return
	var focus := get_viewport().gui_get_focus_owner()
	if focus is LineEdit or focus is TextEdit or get_tree().paused:
		return
	var k: int = e.keycode if e is InputEventKey else 0
	if e is InputEventJoypadButton:
		match e.button_index:
			JOY_BUTTON_A: k = KEY_E
			JOY_BUTTON_B, JOY_BUTTON_START: k = KEY_ESCAPE
			JOY_BUTTON_Y: k = KEY_SPACE if full.visible else KEY_ENTER
			JOY_BUTTON_LEFT_SHOULDER: k = KEY_1
			JOY_BUTTON_RIGHT_SHOULDER: k = KEY_2
	if full.visible:
		if k in [KEY_ESCAPE, KEY_ENTER, KEY_KP_ENTER]:
			fullscreen(false)
		elif k == KEY_E:
			stand()
		elif k == KEY_SPACE:
			_hint_seconds = 4.0
			user_paused = not user_paused
			video.paused = user_paused
		else:
			return
		get_viewport().set_input_as_handled()
	elif viewer.get("seated"):
		if k == KEY_ESCAPE:
			stand()
		elif k in [KEY_1, KEY_KP_1] and titles.size() > 1:
			pick(0)
		elif k in [KEY_2, KEY_KP_2] and titles.size() > 1:
			pick(1)
		elif k in [KEY_ENTER, KEY_KP_ENTER]:
			play()
			fullscreen(true)
		elif k == KEY_SPACE and started:
			user_paused = not user_paused
			video.paused = user_paused
		elif k == KEY_E:
			stand()
		else:
			return
		get_viewport().set_input_as_handled()
	elif k == KEY_E and _near != "" and not viewer.get("fly"):
		sit(_near)
		get_viewport().set_input_as_handled()


func _update_subtitle() -> void:
	var text := ""
	if started:
		var at := video.stream_position
		for cue in captions:
			if at >= float(cue.start) and at < float(cue.end):
				text = str(cue.text)
				break
	if subtitle.text != text:
		subtitle.text = text


func _process(dt: float) -> void:
	_doors(dt)
	_update_subtitle()
	if not viewer:
		return
	var p := viewer.global_position
	var inside := in_hall(p)
	if not inside:
		_near = ""
	if autoplay and inside and viewer.get("seated") and not started:
		play()
	if started:
		video.paused = user_paused or not inside
	var text := ""
	if viewer.get("seated"):
		if not started or user_paused:
			text = "ENTER  PLAY THE FILM      E  STAND UP"
			if titles.size() > 1:
				text = "1  %s     2  %s     ENTER  PLAY     E  STAND UP" % titles
		else:
			text = "ENTER  FULL SCREEN      SPACE  PAUSE      E  STAND UP"
	elif inside:
		_near = nearest_free(p)
		text = ("E  SIT DOWN  (%s)" % seat_label(_near)) if _near != "" else "WALK UP TO A FREE SEAT TO SIT DOWN"
	if full.visible:
		full_hint.text = "PAUSED — SPACE  RESUME     ESC  BACK TO THE HALL" if user_paused else "ESC  BACK TO THE HALL     SPACE  PAUSE"
		_hint_seconds = 4.0 if user_paused else maxf(0.0, _hint_seconds - dt)
		full_hint.modulate.a = clampf(_hint_seconds, 0.0, 1.0)
		text = ""
	if text != _said:
		_said = text
		prompt.emit(text)
