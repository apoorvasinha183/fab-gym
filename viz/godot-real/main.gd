extends Node3D
## The realistic fab to explore: a gigafab-style layout of our own design on the SMT2020 model,
## not a real fab. Built from the film's parts (res://data/models.json, viz/look/kit.py) and
## scene (res://data/scene.json, viz/prep.py --real); viz/godot-real/sync.sh copies them in.
##
## Keys: Tab switches walk and fly. WASD move, the mouse looks, Shift goes faster, Q/E down and
## up when flying. Click a tool for its card. 1 the campus, 2 walk the lithography bay,
## 3 follow the film's lot, 4 over the bays with the roofs cut away, C cut away on or off.
## Space pause, + and - speed, H hide the help, Esc frees the mouse.
##
## Check:  godot --headless --path viz/godot-real -- --check OUT.json
## Still:  godot --path viz/godot-real -- --shot OUT.png VIEW SECONDS

const SCENE := "res://data/scene.json"
const MODELS := "res://data/models.json"
const FILM := "res://data/film.json"
const BADGE := "Fab Gym · a gigafab-style layout of our own design, on the SMT2020 model · not a real fab"
const HELP := "Tab walk or fly · WASD move · mouse look · Shift faster · Q/E down/up when flying\nClick a tool for its card · 1 campus · 2 walk the lithography bay · 3 follow the film's lot · 4 cut away the roofs\nC cut away on/off · Space pause · +/- speed · H hide help · Esc free the mouse"
const STATE_WORDS := ["working", "idle", "maintenance (scheduled)", "broken down"]
const KIND_WORDS := {
	"scanner": "lithography scanner", "track": "coat and develop track", "metrology": "metrology tool",
	"inspection": "inspection tool", "etch": "dry etch cluster", "deposition": "deposition cluster",
	"epitaxy": "epitaxy cluster", "furnace": "vertical furnace", "implanter": "ion implanter",
	"polisher": "polisher (CMP)", "wet_bench": "wet bench", "stocker": "timed hold (stocker)",
}
const LAMP_CHANNEL := {"led_green": 0.0, "led_amber": 1.0, "led_blue": 2.0, "led_red": 3.0}

var S: Dictionary
var M: Dictionary
var F: Dictionary = {}
var CZ: float
var CEIL: float
var AIR_TOP: float
var ROOF_TOP: float
var SUPPORT_TOP: float
var WAFFLE_TOP: float
var PORT_Z: float
var RAIL_Z: float
var SP: float
var DEPTH: float

var mats := {}                 # kit material name -> Material
var lamp_mat: ShaderMaterial
var kind_h := {}               # kind -> model height

# time
var t := 0.0                   # fab minutes
var speed := 1.0               # fab minutes per real second
var paused := false
var state_i := 0
var tool_state: PackedInt32Array
var lamp_set: PackedInt32Array   # what each status light was told to show (the renderer is a dummy when headless)

# tools
var lamp_mm := {}              # kind -> MultiMesh of status lights
var tool_slot: Array = []      # tool -> [kind, instance]
var body_mm := {}              # kind -> MultiMesh of bodies

# lots
var lot_keys: Array = []
var lot_moves: Array = []
var lot_slot: Array = []       # lot -> [MultiMesh or null, instance]
var cursor: PackedInt32Array
var lot_drawn: Array = []      # where each lot was last drawn, in plan coordinates
var car_mm: MultiMesh
var hero := -1
var hero_mi: MeshInstance3D
var lots_mm: MultiMesh
var hot_mm: MultiMesh

# the cut away
var cut := false
var cut_nodes: Array = []

# player and camera
var player: CharacterBody3D
var cam: Camera3D
var walking := false
var yaw := 0.0
var pitch := -0.3
var fly_speed := 12.0
var vel_y := 0.0
var following := false
var sun: DirectionalLight3D
var env: Environment
var lights: Node3D

# ui
var hud: Label
var help: Label
var card: Label
var card_box: PanelContainer
var cross: Control
var far_labels: Array = []

# check and still
var check_out := ""
var check_phase := 0
var check_frames := 0
var check := {}
var script_dir := Vector3.ZERO
var shot := ""
var shot_at := -1.0


static func w(x: float, y: float, z: float) -> Vector3:
	# plan (east, north, up) to Godot (x, up, -north)
	return Vector3(x, z, -y)


static func dirw(v: Array) -> Vector3:
	return Vector3(v[0], v[2], -v[1])


static func plan(p: Vector3) -> Array:
	return [p.x, -p.z, p.y]


# ---------------------------------------------------------------------------- meshes from parts

class Batch:
	## Boxes and cylinders in plan coordinates gathered into one mesh, a surface per material.
	var surf := {}
	var order: Array = []
	var col := Color(1, 1, 1)
	var u := 0.0

	func _s(m: Material) -> SurfaceTool:
		if not surf.has(m):
			var s := SurfaceTool.new()
			s.begin(Mesh.PRIMITIVE_TRIANGLES)
			surf[m] = s
			order.append(m)
		return surf[m]

	func _v(s: SurfaceTool, p: Vector3, n: Vector3) -> void:
		s.set_normal(n)
		s.set_color(col)
		s.set_uv(Vector2(u, 0.0))
		s.add_vertex(p)

	func tri(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, na: Vector3, nb: Vector3, nc: Vector3) -> void:
		# Godot draws clockwise triangles as front faces
		if (b - a).cross(c - a).dot(na + nb + nc) > 0.0:
			_v(s, a, na)
			_v(s, c, nc)
			_v(s, b, nb)
		else:
			_v(s, a, na)
			_v(s, b, nb)
			_v(s, c, nc)

	func quad(s: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3, n: Vector3) -> void:
		tri(s, a, b, c, n, n, n)
		tri(s, a, c, d, n, n, n)

	func box(m: Material, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> void:
		var s := _s(m)
		var a := Vector3(x0, z0, -y0)
		var b := Vector3(x1, z1, -y1)
		var lo := Vector3(minf(a.x, b.x), minf(a.y, b.y), minf(a.z, b.z))
		var hi := Vector3(maxf(a.x, b.x), maxf(a.y, b.y), maxf(a.z, b.z))
		quad(s, Vector3(hi.x, lo.y, lo.z), Vector3(hi.x, hi.y, lo.z), Vector3(hi.x, hi.y, hi.z), Vector3(hi.x, lo.y, hi.z), Vector3.RIGHT)
		quad(s, Vector3(lo.x, lo.y, lo.z), Vector3(lo.x, lo.y, hi.z), Vector3(lo.x, hi.y, hi.z), Vector3(lo.x, hi.y, lo.z), Vector3.LEFT)
		quad(s, Vector3(lo.x, hi.y, lo.z), Vector3(lo.x, hi.y, hi.z), Vector3(hi.x, hi.y, hi.z), Vector3(hi.x, hi.y, lo.z), Vector3.UP)
		quad(s, Vector3(lo.x, lo.y, lo.z), Vector3(hi.x, lo.y, lo.z), Vector3(hi.x, lo.y, hi.z), Vector3(lo.x, lo.y, hi.z), Vector3.DOWN)
		quad(s, Vector3(lo.x, lo.y, hi.z), Vector3(hi.x, lo.y, hi.z), Vector3(hi.x, hi.y, hi.z), Vector3(lo.x, hi.y, hi.z), Vector3.BACK)
		quad(s, Vector3(lo.x, lo.y, lo.z), Vector3(lo.x, hi.y, lo.z), Vector3(hi.x, hi.y, lo.z), Vector3(hi.x, lo.y, lo.z), Vector3.FORWARD)

	func cyl(m: Material, lo: Array, hi: Array, axis := "z", n := 16) -> void:
		var s := _s(m)
		var ia: int = {"x": 0, "y": 1, "z": 2}[axis]
		var o1 := (ia + 1) % 3
		var o2 := (ia + 2) % 3
		var c := [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0]
		var r1: float = (hi[o1] - lo[o1]) / 2.0
		var r2: float = (hi[o2] - lo[o2]) / 2.0
		var r0: Array = []
		var r1s: Array = []
		var ns: Array = []
		for i in n:
			var ang := TAU * i / n
			var p := [0.0, 0.0, 0.0]
			p[o1] = c[o1] + r1 * cos(ang)
			p[o2] = c[o2] + r2 * sin(ang)
			var q := p.duplicate()
			p[ia] = lo[ia]
			q[ia] = hi[ia]
			var nn := [0.0, 0.0, 0.0]
			nn[o1] = cos(ang) * r2
			nn[o2] = sin(ang) * r1
			r0.append(Vector3(p[0], p[2], -p[1]))
			r1s.append(Vector3(q[0], q[2], -q[1]))
			ns.append(Vector3(nn[0], nn[2], -nn[1]).normalized())
		var ax := [0.0, 0.0, 0.0]
		ax[ia] = 1.0
		var up := Vector3(ax[0], ax[2], -ax[1])
		var c0 := [c[0], c[1], c[2]]
		var c1 := [c[0], c[1], c[2]]
		c0[ia] = lo[ia]
		c1[ia] = hi[ia]
		var cc0 := Vector3(c0[0], c0[2], -c0[1])
		var cc1 := Vector3(c1[0], c1[2], -c1[1])
		for i in n:
			var j := (i + 1) % n
			tri(s, r0[i], r0[j], r1s[j], ns[i], ns[j], ns[j])
			tri(s, r0[i], r1s[j], r1s[i], ns[i], ns[j], ns[i])
			tri(s, cc0, r0[j], r0[i], -up, -up, -up)
			tri(s, cc1, r1s[i], r1s[j], up, up, up)

	func mesh() -> ArrayMesh:
		var am := ArrayMesh.new()
		for m in order:
			var s: SurfaceTool = surf[m]
			s.set_material(m)
			s.commit(am)
		return am


func kit_mat(name: String) -> Material:
	if mats.has(name):
		return mats[name]
	var d: Array = M["materials"][name]
	var m := StandardMaterial3D.new()
	var c := Color(d[0])
	c.a = d[4]
	m.albedo_color = c
	m.metallic = d[1]
	m.roughness = d[2]
	if d[3] > 0.0:
		m.emission_enabled = true
		m.emission = Color(d[0])
		m.emission_energy_multiplier = d[3]
	if d[4] < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mats[name] = m
	return m


func pm(hex: String, metal := 0.0, rough := 0.6, emit := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(hex)
	m.metallic = metal
	m.roughness = rough
	if emit > 0.0:
		m.emission_enabled = true
		m.emission = Color(hex)
		m.emission_energy_multiplier = emit
	return m


func add_part(b: Batch, p: Dictionary, m: Material) -> void:
	if p["shape"] == "box":
		var lo: Array = p["min"]
		var hi: Array = p["max"]
		b.box(m, lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
	else:
		b.cyl(m, p["min"], p["max"], p.get("axis", "z"), 16)


func parts_mesh(parts: Array, lights_only: bool) -> ArrayMesh:
	var b := Batch.new()
	for p in parts:
		var is_light: bool = p["role"] == "light"
		if is_light != lights_only:
			continue
		if lights_only:
			b.col = Color(M["materials"][p["mat"]][0]).srgb_to_linear()
			b.u = LAMP_CHANNEL.get(p["mat"], -1.0)
			add_part(b, p, lamp_mat)
		else:
			add_part(b, p, kit_mat(p["mat"]))
	return b.mesh()


func grid_mat(base: String, line: String, cell: Vector3, frac := 0.04, rough := 0.5, metal := 0.0, emit := 0.0, dots := 0) -> StandardMaterial3D:
	## A panelled surface: one panel per texture tile, seams as lines, mapped by world position.
	var n := 128
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var cb := Color(base)
	var cl := Color(line)
	img.fill(cb)
	var lw := maxi(1, int(n * frac))
	for i in n:
		for j in lw:
			img.set_pixel(i, j, cl)
			img.set_pixel(j, i, cl)
	if dots > 0:
		var step := n / dots
		for a in dots:
			for b in dots:
				var cx := a * step + step / 2
				var cy := b * step + step / 2
				for dx in [-1, 0, 1]:
					for dy in [-1, 0, 1]:
						img.set_pixel(clampi(cx + dx, 0, n - 1), clampi(cy + dy, 0, n - 1), cb.lerp(cl, 0.55))
	img.generate_mipmaps()
	var m := StandardMaterial3D.new()
	m.albedo_texture = ImageTexture.create_from_image(img)
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3(1.0 / cell.x, 1.0 / cell.y, 1.0 / cell.z)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	m.roughness = rough
	m.metallic = metal
	if emit > 0.0:
		m.emission_enabled = true
		m.emission_texture = m.albedo_texture
		m.emission = Color(1, 1, 1)
		m.emission_energy_multiplier = emit
	return m


func noise_mat(a: String, b: String, scale: float, rough := 0.9) -> StandardMaterial3D:
	var nt := NoiseTexture2D.new()
	nt.width = 512
	nt.height = 512
	nt.seamless = true
	var fn := FastNoiseLite.new()
	fn.frequency = 0.02
	nt.noise = fn
	var g := Gradient.new()
	g.set_color(0, Color(a))
	g.set_color(1, Color(b))
	nt.color_ramp = g
	var m := StandardMaterial3D.new()
	m.albedo_texture = nt
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE / scale
	m.roughness = rough
	return m


func node(mesh: Mesh, name: String, shadows := true) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.name = name
	if not shadows:
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	return mi


func make(b: Batch, name: String, shadows := true) -> MeshInstance3D:
	return node(b.mesh(), name, shadows)


# ---------------------------------------------------------------------------- start

func _ready() -> void:
	var f := FileAccess.open(SCENE, FileAccess.READ)
	var g := FileAccess.open(MODELS, FileAccess.READ)
	if f == null or g == null:
		push_error("no data: run viz/godot-real/sync.sh from the repo root")
		get_tree().quit(1)
		return
	S = JSON.parse_string(f.get_as_text())
	M = JSON.parse_string(g.get_as_text())
	if FileAccess.file_exists(FILM):
		F = JSON.parse_string(FileAccess.open(FILM, FileAccess.READ).get_as_text())
	var floors := {}
	for fl in S["floors"]:
		floors[fl["name"]] = fl
	CZ = S["clean_z"]
	CEIL = CZ + floors["cleanroom"]["z1"] - floors["cleanroom"]["z0"]
	AIR_TOP = floors["air space"]["z1"]
	ROOF_TOP = floors["roof"]["z1"]
	SUPPORT_TOP = floors["support floor"]["z1"]
	WAFFLE_TOP = floors["waffle slab"]["z1"]
	PORT_Z = S["port_z"]
	RAIL_Z = S["rail_z"]
	SP = S["spine"]
	DEPTH = S["depth"]
	var args := OS.get_cmdline_user_args()
	var ci := args.find("--check")
	if ci >= 0:
		check_out = args[ci + 1]
	var si := args.find("--shot")
	t = S["from"]
	_environment()
	_lamp_material()
	_campus()
	_fabs()
	_rails()
	_tools()
	_lots()
	_player()
	_hud()
	_apply_states_until(t)
	_place_lots()
	view(1)
	if si >= 0:
		shot = args[si + 1]
		view(int(args[si + 2]))
		shot_at = float(args[si + 3])
	if check_out != "":
		t = float(S["from"]) + 120.0
		_apply_states_until(t)
		_place_lots()
		_check_start()


func _environment() -> void:
	env = Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color("4d79b3")
	sm.sky_horizon_color = Color("c9d6e3")
	sm.ground_horizon_color = Color("c9d6e3")
	sm.ground_bottom_color = Color("5d6b5a")
	sky.sky_material = sm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.0
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.glow_enabled = true
	env.glow_intensity = 0.35
	env.glow_bloom = 0.04
	env.glow_hdr_threshold = 1.2
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssao_intensity = 1.6
	env.fog_enabled = true
	env.fog_light_color = Color("c9d6e3")
	env.fog_density = 0.00006
	env.fog_aerial_perspective = 0.25
	env.ssil_enabled = true
	env.ssil_intensity = 0.8
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)
	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, -32, 0)
	sun.light_energy = 1.8
	sun.light_color = Color("ffe9cc")
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 450.0
	add_child(sun)
	lights = Node3D.new()
	lights.name = "inside lights"
	add_child(lights)


func _lamp_material() -> void:
	var sh := Shader.new()
	sh.code = """
shader_type spatial;
render_mode cull_disabled;
varying float lit;
void vertex() {
	lit = (UV.x >= 0.0 && abs(UV.x - INSTANCE_CUSTOM.r) < 0.25) ? 1.0 : 0.0;
}
void fragment() {
	ALBEDO = COLOR.rgb * mix(0.12, 1.0, lit);
	EMISSION = COLOR.rgb * lit * 6.0;
	ROUGHNESS = 0.3;
}
"""
	lamp_mat = ShaderMaterial.new()
	lamp_mat.shader = sh


# ---------------------------------------------------------------------------- the campus

var M_GRASS := noise_mat("4d6a3c", "6f8a52", 60.0, 0.95)
var M_CONC := grid_mat("b5b2aa", "9d9a93", Vector3(6, 6, 6), 0.012, 0.9)
var M_ASPHALT := pm("3b3d40", 0.0, 0.85)
var M_MARK := pm("e9e6dc", 0.0, 0.6)
var M_PARK := pm("4a4c50", 0.0, 0.85)
var M_FACADE := grid_mat("d6dadd", "aeb4ba", Vector3(1.2, 2.75, 1.2), 0.015, 0.5, 0.1)
var M_LOUVRE := grid_mat("8f979f", "5e656c", Vector3(4.0, 0.25, 4.0), 0.25, 0.5, 0.4)
var M_BAND := pm("5c6670", 0.3, 0.45)
var M_ROOF := grid_mat("9aa1a8", "7d848b", Vector3(3.0, 3.0, 3.0), 0.03, 0.8, 0.1)
var M_DUCT := pm("c4c9ce", 0.7, 0.35)
var M_FAN := pm("6b737b", 0.6, 0.4)
var M_TANK := pm("e7e9eb", 0.5, 0.3)
var M_STEEL := pm("aab2ba", 0.8, 0.35)
var M_GLASS := pm("9ec3d8", 0.2, 0.1)
var M_CURTAIN := grid_mat("5f7f96", "2e3a44", Vector3(1.5, 3.6, 1.5), 0.04, 0.12, 0.5)
var M_TRUNK := pm("5a4632", 0.0, 0.9)
var M_LEAF := [pm("3f6b35", 0.0, 0.9), pm("4f7d3c", 0.0, 0.9), pm("355c2e", 0.0, 0.9)]
var M_CAR := [pm("e8e8e8", 0.5, 0.3), pm("23262b", 0.5, 0.3), pm("8a9198", 0.5, 0.3), pm("7a1f1f", 0.5, 0.3), pm("1f3a5f", 0.5, 0.3)]
var M_CARGLASS := pm("1b2530", 0.3, 0.1)
var M_TYRE := pm("161616", 0.0, 0.8)
var M_SLAB := grid_mat("a7a49d", "8f8c86", Vector3(1.2, 1.2, 1.2), 0.25, 0.85)
var M_PUMP := pm("8d959d", 0.5, 0.45)
var M_SCRUB := pm("d9dcdf", 0.2, 0.5)
var M_PIPES := [pm("d7dbe0", 0.8, 0.3), pm("4a7fb0", 0.3, 0.4), pm("e2b33c", 0.3, 0.4), pm("6aa36a", 0.3, 0.4)]
var M_STRIP := pm("ffffff", 0.0, 0.3, 3.0)
var M_PLENUM := pm("6e737a", 0.3, 0.6)
var M_TILE := grid_mat("dfe3e7", "a9b0b7", Vector3(0.6, 0.6, 0.6), 0.02, 0.35, 0.1, 0.0, 8)
var M_YELLOW := pm("f2c230", 0.0, 0.5)
var M_WALL := grid_mat("e6e9ec", "b4bac1", Vector3(1.2, 2.75, 1.2), 0.01, 0.5, 0.1)
var M_FFU := grid_mat("f2f4f6", "8a929b", Vector3(1.2, 1.2, 0.6), 0.035, 0.6, 0.0, 0.55)
var M_FFU_Y := grid_mat("f6b93e", "7a5a10", Vector3(1.2, 1.2, 0.6), 0.035, 0.6, 0.0, 0.45)
var M_FFU_TOP := pm("b9bec4", 0.3, 0.6)
var M_RAIL := pm("aeb7c2", 0.9, 0.3)
var M_HANGER := pm("8c949c", 0.8, 0.4)
var M_SHELF := pm("9ca6b1", 0.8, 0.35)


func _label(text: String, p: Vector3, size: int, far: bool) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.position = p
	l.font_size = size
	l.outline_size = size / 6
	l.modulate = Color("f4f7fb")
	l.outline_modulate = Color(0.05, 0.08, 0.12, 0.85)
	if far:
		l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l.fixed_size = true
		l.pixel_size = 0.0007
		l.no_depth_test = true
		far_labels.append(l)
	else:
		l.pixel_size = 0.006
	add_child(l)
	return l


func _car(b: Batch, x: float, y: float, along_x: bool, m: Material) -> void:
	var L := 4.4 if along_x else 1.8
	var W := 1.8 if along_x else 4.4
	b.box(m, x - L / 2, y - W / 2, 0.3, x + L / 2, y + W / 2, 0.95)
	var l2 := 2.4 if along_x else 1.6
	var w2 := 1.6 if along_x else 2.4
	b.box(M_CARGLASS, x - l2 / 2, y - w2 / 2, 0.95, x + l2 / 2, y + w2 / 2, 1.42)
	for du in [-1.4, 1.4]:
		for dv in [-0.8, 0.8]:
			if along_x:
				b.cyl(M_TYRE, [x + du - 0.33, y + dv - 0.12, 0.0], [x + du + 0.33, y + dv + 0.12, 0.66], "y", 10)
			else:
				b.cyl(M_TYRE, [x + dv - 0.12, y + du - 0.33, 0.0], [x + dv + 0.12, y + du + 0.33, 0.66], "x", 10)


func _campus() -> void:
	var G: Dictionary = S["ground"]
	var gb := Batch.new()
	gb.box(M_GRASS, G["x0"] - 6000, G["y0"] - 6000, -0.4, G["x1"] + 6000, G["y1"] + 6000, -0.05)
	make(gb, "ground", false)
	var ground := StaticBody3D.new()
	var gs := CollisionShape3D.new()
	var plane := WorldBoundaryShape3D.new()
	gs.shape = plane
	ground.add_child(gs)
	add_child(ground)
	var camp: Array = S["campus"]
	var x0 := INF
	var x1 := -INF
	var y0 := INF
	var y1 := -INF
	for c in camp:
		if c["kind"] in ["fab", "pad", "cub", "upw", "office", "gas"]:
			x0 = minf(x0, c["x0"])
			x1 = maxf(x1, c["x1"])
		if c["kind"] != "road":
			y0 = minf(y0, c["y0"])
		if c["kind"] in ["fab", "office", "gas"]:
			y1 = maxf(y1, c["y1"])
	x0 -= 25
	x1 += 25
	y0 -= 20
	y1 += 15
	var site := Batch.new()
	site.box(M_CONC, x0, y0, -0.05, x1, y1, 0.0)
	var b := Batch.new()
	for c in camp:
		var k: String = c["kind"]
		var X0: float = c["x0"]
		var X1: float = c["x1"]
		var Y0: float = c["y0"]
		var Y1: float = c["y1"]
		var H: float = c["h"]
		match k:
			"road":
				site.box(M_ASPHALT, X0, Y0, 0.0, X1, Y1, 0.04)
				if X1 - X0 > Y1 - Y0:
					var ym := (Y0 + Y1) / 2
					site.box(M_MARK, X0, ym - 0.08, 0.04, X1, ym + 0.08, 0.045)
				else:
					var xm := (X0 + X1) / 2
					site.box(M_MARK, xm - 0.08, Y0, 0.04, xm + 0.08, Y1, 0.045)
			"parking":
				site.box(M_PARK, X0, Y0, 0.0, X1, Y1, 0.04)
				var rng := RandomNumberGenerator.new()
				rng.seed = 11
				var cb := Batch.new()
				for i in int((X1 - X0) / 2.6):
					for j in int((Y1 - Y0) / 5.2):
						if rng.randf() < 0.55:
							_car(cb, X0 + (i + 0.5) * 2.6, Y0 + (j + 0.5) * 5.2, false, M_CAR[rng.randi() % M_CAR.size()])
				make(cb, "parked cars")
			"pad":
				b.box(M_CONC, X0, Y0, 0.0, X1, Y1, 0.3)
				for i in int((X1 - X0) / 12):
					b.box(M_STEEL, X0 + 6 + i * 12, Y0 + 6, 0.3, X0 + 6.8 + i * 12, Y0 + 6.8, 4.0)
					b.box(M_STEEL, X0 + 6 + i * 12, Y1 - 6.8, 0.3, X0 + 6.8 + i * 12, Y1 - 6, 4.0)
				_label("Pad for Phase 3", w((X0 + X1) / 2, (Y0 + Y1) / 2, 10), 40, true)
			"cub", "upw":
				b.box(M_FACADE, X0, Y0, 0.0, X1, Y1, H - 0.6)
				b.box(M_LOUVRE, X0 - 0.05, Y0 - 0.05, H * 0.55, X1 + 0.05, Y1 + 0.05, H * 0.85)
				b.box(M_ROOF, X0, Y0, H - 0.6, X1, Y1, H)
				for i in int((X1 - X0) / 18):
					var x := X0 + 9 + i * 18
					b.box(M_DUCT, x - 3, Y0 + 8, H, x + 3, Y0 + 20, H + 3.2)
					b.cyl(M_FAN, [x - 2.2, Y1 - 14.4, H], [x + 2.2, Y1 - 10, H + 2.5], "z", 20)
				if k == "upw":
					for i in 4:
						var x := X0 + 12 + i * ((X1 - X0 - 24) / 3)
						b.cyl(M_TANK, [x - 4, Y1 + 3, 0], [x + 4, Y1 + 11, 12], "z", 28)
				_label(c["label"], w((X0 + X1) / 2, (Y0 + Y1) / 2, H + 6), 40, true)
			"office":
				b.box(M_CURTAIN, X0, Y0, 0.0, X1, Y1, H)
				b.box(M_ROOF, X0, Y0, H - 0.5, X1, Y1, H + 0.6)
				b.box(M_CONC, X0 + 20, Y0 - 6, 4.0, X0 + 50, Y0, 4.5)
				_label(c["label"], w((X0 + X1) / 2, (Y0 + Y1) / 2, H + 6), 40, true)
			"gas":
				b.box(M_CONC, X0, Y0, 0.0, X1, Y1, 0.3)
				for i in 6:
					var x := X0 + 8 + i * 9
					b.box(M_TANK, x, Y1 - 16, 0.3, x + 2.4, Y1 - 4, 2.9)
				_label(c["label"], w((X0 + X1) / 2, (Y0 + Y1) / 2, 28), 40, true)
			"tank":
				var cx := (X0 + X1) / 2
				var cy := (Y0 + Y1) / 2
				var r := (X1 - X0) / 2
				b.cyl(M_TANK, [cx - r, cy - r, 0.3], [cx + r, cy + r, H], "z", 28)
				b.cyl(M_STEEL, [cx - r * 1.05, cy - r * 1.05, 0.3], [cx + r * 1.05, cy + r * 1.05, 1.2], "z", 28)
			"cooling_tower":
				b.box(M_LOUVRE, X0, Y0, 0, X1, Y1, H - 0.4)
				b.box(M_ROOF, X0, Y0, H - 0.4, X1, Y1, H)
				var cx := (X0 + X1) / 2
				var cy := (Y0 + Y1) / 2
				b.cyl(M_FAN, [cx - 4.5, cy - 4.5, H], [cx + 4.5, cy + 4.5, H + 3.0], "z", 28)
				if c["label"]:
					_label("Cooling towers", w(cx, cy, H + 16), 40, true)
			"stack":
				var cx := (X0 + X1) / 2
				var cy := (Y0 + Y1) / 2
				b.cyl(M_DUCT, [cx - 1.5, cy - 1.5, 0], [cx + 1.5, cy + 1.5, H], "z", 24)
				b.cyl(M_STEEL, [cx - 1.7, cy - 1.7, H - 1.0], [cx + 1.7, cy + 1.7, H], "z", 24)
			"corridor":
				b.box(M_FACADE, X0, Y0, c["z0"], X1, Y1, H)
			"bridge":
				var z0: float = c["z0"]
				b.box(M_GLASS, X0, Y0, z0, X1, Y0 + 0.1, H)
				b.box(M_GLASS, X0, Y1 - 0.1, z0, X1, Y1, H)
				b.box(M_STEEL, X0, Y0, z0 - 0.6, X1, Y1, z0)
				b.box(M_STEEL, X0, Y0, H, X1, Y1, H + 0.5)
				var n := int((X1 - X0) / 6)
				for i in n + 1:
					var x := X0 + i * (X1 - X0) / n
					b.box(M_STEEL, x - 0.15, Y0 - 0.1, z0, x + 0.15, Y0 + 0.15, H)
					b.box(M_STEEL, x - 0.15, Y1 - 0.15, z0, x + 0.15, Y1 + 0.1, H)
				var xm := (X0 + X1) / 2
				b.box(M_CONC, xm - 1.2, -1.2, 0, xm + 1.2, 1.2, z0 - 0.6)
				_label("Overhead hoist bridge", w(xm, 0, H + 8), 36, true)
	make(site, "site", false)
	make(b, "campus")
	# trees, drawn only
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var tb := Batch.new()
	for i in 240:
		var side := rng.randf()
		var x := 0.0
		var y := 0.0
		if side < 0.3:
			x = rng.randf_range(x0, x1)
			y = rng.randf_range(y1 + 6, y1 + 26)
		elif side < 0.6:
			x = rng.randf_range(x0, x1)
			y = rng.randf_range(y0 - 70, y0 - 8)
		elif side < 0.8:
			x = rng.randf_range(x0 - 40, x0 - 6)
			y = rng.randf_range(y0, y1)
		else:
			x = rng.randf_range(x1 + 6, x1 + 40)
			y = rng.randf_range(y0, y1)
		var clear := true
		for c in camp:
			if c["x0"] - 3 < x and x < c["x1"] + 3 and c["y0"] - 3 < y and y < c["y1"] + 3:
				clear = false
				break
		if not clear:
			continue
		var h := rng.randf_range(6, 11)
		var r := rng.randf_range(2.2, 3.6)
		tb.cyl(M_TRUNK, [x - 0.25, y - 0.25, 0], [x + 0.25, y + 0.25, h * 0.45], "z", 8)
		tb.cyl(M_LEAF[rng.randi() % 3], [x - r, y - r, h * 0.35], [x + r, y + r, h], "z", 10)
	make(tb, "trees")


# ---------------------------------------------------------------------------- the fab buildings

func _solid(body: StaticBody3D, x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, meta := -1) -> void:
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(absf(x1 - x0), absf(z1 - z0), absf(y1 - y0))
	cs.shape = bs
	cs.position = w((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
	if meta >= 0:
		cs.set_meta("tool", meta)
	body.add_child(cs)


func _cuttable(mi: MeshInstance3D) -> void:
	cut_nodes.append(mi)


func _fabs() -> void:
	var walls := StaticBody3D.new()
	walls.name = "walls"
	add_child(walls)
	var fabs: Array = []
	for c in S["campus"]:
		if c["kind"] == "fab":
			fabs.append(c)
	for ph in fabs.size():
		var c: Dictionary = fabs[ph]
		var X0: float = c["x0"]
		var X1: float = c["x1"]
		var Y0: float = c["y0"]
		var Y1: float = c["y1"]
		var ox: float = S["offsets"][ph]
		var L: float = S["lengths"][ph]
		var ix0 := ox
		var ix1 := ox + L
		var pre: String = c["name"]
		# support floor
		var sb := Batch.new()
		sb.box(M_CONC, X0, Y0, -0.05, X1, Y1, 0.0)
		for gx in int((X1 - X0) / 12) + 1:
			for gy in int((Y1 - Y0) / 12) + 1:
				var x := X0 + 3 + gx * 12
				var y := Y0 + 3 + gy * 12
				if x < X1 - 1 and y < Y1 - 1 and absf(y) > SP / 2 + 0.5:
					sb.box(M_SLAB, x - 0.4, y - 0.4, 0, x + 0.4, y + 0.4, SUPPORT_TOP)
		for tl in S["tools"]:
			if S["bays"][tl["bay"]]["phase"] != ph:
				continue
			var cx: float = (tl["x0"] + tl["x1"]) / 2
			var cy: float = (tl["y0"] + tl["y1"]) / 2
			sb.box(M_PUMP, cx - 0.35, cy - 0.5, 0, cx + 0.35, cy + 0.5, 1.0)
			var back: float = tl["x0"] - 0.5 if tl["wall"] == 0 else tl["x1"] + 0.5
			sb.cyl(M_SCRUB, [back - 0.4, cy - 0.4, 0], [back + 0.4, cy + 0.4, 1.9], "z", 12)
			sb.cyl(M_PIPES[0], [cx - 0.08, cy - 0.08, 1.0], [cx + 0.08, cy + 0.08, SUPPORT_TOP], "z", 8)
		for bay in S["bays"]:
			if bay["phase"] != ph:
				continue
			for xx in [bay["x0"] + 0.9, bay["x1"] - 0.9]:
				sb.cyl(M_DUCT, [xx - 0.45, bay["y0"], 4.6], [xx + 0.45, bay["y1"], 5.5], "y", 14)
		var ys := [-2.4, -1.4, -0.4, 0.6, 1.6, 2.6]
		for i in ys.size():
			sb.cyl(M_PIPES[i % M_PIPES.size()], [ix0, ys[i] - 0.25, 4.3], [ix1, ys[i] + 0.25, 4.8], "x", 12)
		sb.box(M_STEEL, ix0, -3.0, 4.0, ix1, 3.0, 4.1)
		for gy in int((Y1 - Y0) / 8):
			var y := Y0 + 4 + gy * 8
			sb.box(M_STRIP, X0 + 1, y - 0.06, SUPPORT_TOP - 0.12, X1 - 1, y + 0.06, SUPPORT_TOP - 0.05)
		make(sb, pre + " support floor")
		# waffle slab, plenum and tiles
		var wb := Batch.new()
		wb.box(M_SLAB, X0, Y0, SUPPORT_TOP, X1, Y1, WAFFLE_TOP)
		wb.box(M_PLENUM, X0, Y0, WAFFLE_TOP, X1, Y1, CZ - 0.04)
		wb.box(M_TILE, X0, Y0, CZ - 0.04, X1, Y1, CZ)
		for y in [-SP / 2 - 0.08, SP / 2]:
			wb.box(M_YELLOW, ix0, y, CZ, ix1, y + 0.08, CZ + 0.005)
		make(wb, pre + " floors")
		_solid(walls, X0, Y0, SUPPORT_TOP, X1, Y1, CZ)
		# bay walls between bays, from the spine to the back wall
		var bw := Batch.new()
		for side in [0, 1]:
			var sgn := 1.0 if side == 0 else -1.0
			var xs := {}
			for bay in S["bays"]:
				if bay["phase"] == ph and bay["side"] == side:
					xs[snappedf(bay["x0"], 0.001)] = true
					xs[snappedf(bay["x1"], 0.001)] = true
			var bx: Array = xs.keys()
			bx.sort()
			var ya := sgn * (SP / 2)
			var yb := sgn * (SP / 2 + DEPTH)
			for i in range(1, bx.size() - 1):
				bw.box(M_WALL, bx[i] - 0.06, minf(ya, yb), CZ, bx[i] + 0.06, maxf(ya, yb), CEIL)
				_solid(walls, bx[i] - 0.06, minf(ya, yb), CZ, bx[i] + 0.06, maxf(ya, yb), CEIL)
		for bay in S["bays"]:
			if bay["phase"] != ph:
				continue
			var cx: float = (bay["x0"] + bay["x1"]) / 2
			var ysg := SP / 2 + 0.2 if bay["side"] == 0 else -SP / 2 - 0.2
			var sign_m := pm(S["areas"][bay["area"]]["colour"].trim_prefix("#"), 0.0, 0.5, 0.4)
			bw.box(sign_m, cx - 1.6, ysg - 0.03, CEIL - 1.1, cx + 1.6, ysg + 0.03, CEIL - 0.5)
			var lab := _label(S["areas"][bay["area"]]["name"], w(cx, ysg + (-0.05 if bay["side"] == 0 else 0.05), CEIL - 0.8), 64, false)
			lab.modulate = Color("15191e")
			lab.outline_size = 0
			if bay["side"] == 1:
				lab.rotation_degrees = Vector3(0, 180, 0)
		for sgn in [1.0, -1.0]:
			var ye: float = sgn * (SP / 2 + DEPTH)
			bw.box(M_WALL, ix0, ye - 0.06, CZ, ix1, ye + 0.06, CEIL)
			_solid(walls, ix0, ye - 0.06, CZ, ix1, ye + 0.06, CEIL)
		make(bw, pre + " bay walls")
		# the filter ceiling: yellow over lithography, white elsewhere
		var ce := Batch.new()
		for bay in S["bays"]:
			if bay["phase"] != ph:
				continue
			ce.box(M_FFU_Y if bay["light"] == "yellow" else M_FFU, bay["x0"], bay["y0"], CEIL, bay["x1"], bay["y1"], CEIL + 0.12)
		ce.box(M_FFU, ix0, -SP / 2, CEIL, ix1, SP / 2, CEIL + 0.12)
		ce.box(M_FFU_TOP, X0, Y0, CEIL + 0.12, X1, Y1, CEIL + 0.14)
		_cuttable(make(ce, pre + " ceiling"))
		# the air space
		var ab := Batch.new()
		for gx in int((X1 - X0) / 12) + 1:
			var x := X0 + 3 + gx * 12
			if x < X1:
				ab.box(M_STEEL, x - 0.2, Y0, AIR_TOP - 0.9, x + 0.2, Y1, AIR_TOP - 0.1)
				for gy in int((Y1 - Y0) / 12) + 1:
					var y := Y0 + 3 + gy * 12
					if y < Y1:
						ab.box(M_STEEL, x - 0.15, y - 0.15, CEIL + 0.14, x + 0.15, y + 0.15, AIR_TOP - 0.9)
		for y in [-48, -20, 20, 48]:
			ab.cyl(M_DUCT, [X0 + 1, y - 0.9, CEIL + 1.4], [X1 - 1, y + 0.9, CEIL + 3.2], "x", 20)
		_cuttable(make(ab, pre + " air space"))
		# roof and rooftop plant
		var rb := Batch.new()
		rb.box(M_ROOF, X0, Y0, AIR_TOP, X1, Y1, ROOF_TOP)
		for i in int((X1 - X0) / 24):
			var x := X0 + 12 + i * 24
			for y in [Y0 + 18, Y1 - 30]:
				rb.box(M_DUCT, x - 5, y, ROOF_TOP, x + 5, y + 12, ROOF_TOP + 3.5)
				rb.cyl(M_FAN, [x - 1.8, y + 3, ROOF_TOP + 3.5], [x + 1.8, y + 6.6, ROOF_TOP + 4.6], "z", 20)
		_cuttable(make(rb, pre + " roof"))
		# the facade in bands; the upper two go with the roof when cut away
		var T := 0.4
		var low := Batch.new()
		var high := Batch.new()
		for f in [[X0, Y0, X1, Y0 + T], [X0, Y1 - T, X1, Y1], [X0, Y0, X0 + T, Y1], [X1 - T, Y0, X1, Y1]]:
			low.box(M_LOUVRE, f[0], f[1], 0.0, f[2], f[3], WAFFLE_TOP)
			low.box(M_FACADE, f[0], f[1], WAFFLE_TOP, f[2], f[3], CEIL + 0.14)
			var zz := (WAFFLE_TOP + CEIL) / 2
			low.box(M_BAND, f[0] - 0.02, f[1] - 0.02, zz - 0.4, f[2] + 0.02, f[3] + 0.02, zz + 0.4)
			high.box(M_FACADE, f[0], f[1], CEIL + 0.14, f[2], f[3], AIR_TOP)
			high.box(M_BAND, f[0], f[1], AIR_TOP, f[2], f[3], ROOF_TOP + 0.8)
			_solid(walls, f[0], f[1], CZ, f[2], f[3], CEIL)
		make(low, pre + " facade")
		_cuttable(make(high, pre + " facade top"))
		_label("Phase %d fab" % (ph + 1), w((X0 + X1) / 2, (Y0 + Y1) / 2, ROOF_TOP + 14), 44, true)
		# inside lights: down each bay's aisle and along the spine
		for bay in S["bays"]:
			if bay["phase"] != ph:
				continue
			var cx: float = (bay["x0"] + bay["x1"]) / 2
			var yellow: bool = bay["light"] == "yellow"
			var y := float(bay["y0"]) + 5.0
			while y < float(bay["y1"]) - 2.0:
				_lamp(w(cx, y, CEIL - 0.6), yellow)
				y += 10.0
		var x := ix0 + 6.0
		while x < ix1:
			_lamp(w(x, 0.0, CEIL - 0.6), false)
			x += 12.0


func _lamp(p: Vector3, yellow: bool) -> void:
	var l := OmniLight3D.new()
	l.position = p
	l.omni_range = 11.0
	l.light_energy = 1.4 if yellow else 1.1
	l.light_color = Color(1.0, 0.68, 0.22) if yellow else Color(0.94, 0.97, 1.0)
	l.distance_fade_enabled = true
	l.distance_fade_begin = 70.0
	l.distance_fade_length = 20.0
	lights.add_child(l)


# ---------------------------------------------------------------------------- rails, shelves, stockers

func _rails() -> void:
	var rb := Batch.new()
	for r in S["rails"]:
		var a: Array = r[0]
		var b: Array = r[1]
		var wd := 0.08
		rb.box(M_RAIL, minf(a[0], b[0]) - wd, minf(a[1], b[1]) - wd, a[2], maxf(a[0], b[0]) + wd, maxf(a[1], b[1]) + wd, a[2] + 0.12)
		var L := Vector2(a[0], a[1]).distance_to(Vector2(b[0], b[1]))
		var n := maxi(1, int(L / 3))
		for i in n + 1:
			var x: float = a[0] + (b[0] - a[0]) * i / n
			var y: float = a[1] + (b[1] - a[1]) * i / n
			rb.box(M_HANGER, x - 0.02, y - 0.02, a[2] + 0.12, x + 0.02, y + 0.02, CEIL)
	make(rb, "hoist rails")
	var shelves := {}
	for lot in S["lots"]:
		var k: Array = lot["k"]
		for i in k.size() - 1:
			var a: Array = k[i]
			var b: Array = k[i + 1]
			if a[1] == b[1] and a[2] == b[2] and a[3] == b[3] and a[3] > PORT_Z + 0.01 and absf(a[2]) > SP / 2:
				shelves[Vector3(snappedf(a[1], 0.01), snappedf(a[2], 0.01), snappedf(a[3], 0.001))] = true
	var sh := Batch.new()
	var fw: float = S["foup"][0]
	var fd: float = S["foup"][1]
	for p in shelves:
		sh.box(M_SHELF, p.x - fw / 2 - 0.03, p.y - fd / 2 - 0.03, p.z - 0.03, p.x + fw / 2 + 0.03, p.y + fd / 2 + 0.03, p.z)
		sh.box(M_HANGER, p.x - 0.015, p.y - 0.015, p.z, p.x + 0.015, p.y + 0.015, CEIL)
	make(sh, "shelves")


# ---------------------------------------------------------------------------- tools

func _height(parts: Array) -> float:
	var h := 0.0
	for p in parts:
		if p["role"] != "light":
			h = maxf(h, p["max"][2])
	return h


func _xf(o: Array, yaw_deg: float) -> Transform3D:
	return Transform3D(Basis(Vector3.UP, deg_to_rad(yaw_deg)), w(o[0], o[1], o[2]))


func _tools() -> void:
	var by_kind := {}
	for i in S["tools"].size():
		var k: String = S["tools"][i]["kind"]
		if not by_kind.has(k):
			by_kind[k] = []
		by_kind[k].append(i)
	tool_slot.resize(S["tools"].size())
	tool_state.resize(S["tools"].size())
	tool_state.fill(1)
	lamp_set.resize(S["tools"].size())
	lamp_set.fill(1)
	var solids := StaticBody3D.new()
	solids.name = "tool bodies"
	solids.collision_layer = 3
	add_child(solids)
	for k in M["kinds"]:
		kind_h[k] = _height(M["kinds"][k])
	for k in by_kind:
		var ids: Array = by_kind[k]
		var body := MultiMesh.new()
		body.transform_format = MultiMesh.TRANSFORM_3D
		body.mesh = parts_mesh(M["kinds"][k], false)
		body.instance_count = ids.size()
		var lamp := MultiMesh.new()
		lamp.transform_format = MultiMesh.TRANSFORM_3D
		lamp.use_custom_data = true
		lamp.mesh = parts_mesh(M["kinds"][k], true)
		lamp.instance_count = ids.size()
		for j in ids.size():
			var tl: Dictionary = S["tools"][ids[j]]
			var xf := _xf(tl["o"], tl["yaw"])
			body.set_instance_transform(j, xf)
			lamp.set_instance_transform(j, xf)
			lamp.set_instance_custom_data(j, Color(1.0, 0, 0, 0))
			tool_slot[ids[j]] = [k, j]
			_solid(solids, tl["x0"], tl["y0"], CZ, tl["x1"], tl["y1"], CZ + float(tl["h"]), ids[j])
		var bi := MultiMeshInstance3D.new()
		bi.multimesh = body
		bi.name = k
		add_child(bi)
		var li := MultiMeshInstance3D.new()
		li.multimesh = lamp
		li.name = k + " lights"
		li.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(li)
		body_mm[k] = body
		lamp_mm[k] = lamp
	# stockers along the spine
	var st := MultiMesh.new()
	st.transform_format = MultiMesh.TRANSFORM_3D
	st.mesh = parts_mesh(M["kinds"]["stocker"], false)
	st.instance_count = S["stockers"].size()
	for i in S["stockers"].size():
		var s: Dictionary = S["stockers"][i]
		st.set_instance_transform(i, _xf(s["o"], s["yaw"]))
		_solid(solids, s["x0"], s["y0"], CZ, s["x1"], s["y1"], CZ + float(kind_h["stocker"]))
	var sti := MultiMeshInstance3D.new()
	sti.multimesh = st
	sti.name = "stockers"
	add_child(sti)


func _show_lamp(i: int, s: int) -> void:
	var slot: Array = tool_slot[i]
	lamp_mm[slot[0]].set_instance_custom_data(slot[1], Color(float(s), 0, 0, 0))
	lamp_set[i] = s


func _apply_states_until(now: float) -> void:
	var st: Array = S["states"]
	while state_i < st.size() and float(st[state_i][0]) <= now:
		var e: Array = st[state_i]
		var i := int(e[1])
		var s := int(e[2])
		if tool_state[i] != s:
			tool_state[i] = s
			_show_lamp(i, s)
		state_i += 1


func _reset_states() -> void:
	state_i = 0
	for i in tool_state.size():
		tool_state[i] = -1
	_apply_states_until(t)
	for i in tool_state.size():
		if tool_state[i] == -1:
			tool_state[i] = 1
			_show_lamp(i, 1)


# ---------------------------------------------------------------------------- lots and hoist cars

func _carrier_mesh(shell: Material, tag: String) -> ArrayMesh:
	var b := Batch.new()
	for p in M["carrier"]:
		add_part(b, p, shell if p["mat"] == "foup_shell" else kit_mat(p["mat"]))
	if tag != "":
		var fw: float = S["foup"][0]
		var fh: float = S["foup"][2]
		b.box(pm(tag, 0.0, 0.4, 5.0), -fw / 2 - 0.004, -0.06, fh - 0.1, fw / 2 + 0.004, 0.06, fh - 0.06)
	return b.mesh()


func _lots() -> void:
	var lots: Array = S["lots"]
	var hero_id: String = F.get("lot", "")
	var plain: Array = []
	var hot: Array = []
	for i in lots.size():
		lot_keys.append(lots[i]["k"])
		lot_moves.append(lots[i]["m"])
		if lots[i]["id"] == hero_id:
			hero = i
		elif lots[i]["hot"]:
			hot.append(i)
		else:
			plain.append(i)
	cursor.resize(lots.size())
	cursor.fill(0)
	lot_drawn.resize(lots.size())
	lot_slot.resize(lots.size())
	lots_mm = MultiMesh.new()
	lots_mm.transform_format = MultiMesh.TRANSFORM_3D
	lots_mm.mesh = _carrier_mesh(pm("2f353c", 0.1, 0.35), "")
	lots_mm.instance_count = plain.size()
	for j in plain.size():
		lot_slot[plain[j]] = [lots_mm, j]
	hot_mm = MultiMesh.new()
	hot_mm.transform_format = MultiMesh.TRANSFORM_3D
	hot_mm.mesh = _carrier_mesh(pm("c4582a", 0.1, 0.35), "ff7a1a")
	hot_mm.instance_count = hot.size()
	for j in hot.size():
		lot_slot[hot[j]] = [hot_mm, j]
	for mm in [lots_mm, hot_mm]:
		var mi := MultiMeshInstance3D.new()
		mi.multimesh = mm
		add_child(mi)
	if hero >= 0:
		hero_mi = node(_carrier_mesh(pm("2f353c", 0.1, 0.35), "39d5ff"), "the film's lot")
		lot_slot[hero] = [null, 0]
	var vb := Batch.new()
	for p in M["vehicle"]:
		add_part(vb, p, kit_mat(p["mat"]))
	car_mm = MultiMesh.new()
	car_mm.transform_format = MultiMesh.TRANSFORM_3D
	car_mm.mesh = vb.mesh()
	car_mm.instance_count = lots.size()
	var ci := MultiMeshInstance3D.new()
	ci.multimesh = car_mm
	ci.name = "hoist cars"
	add_child(ci)


func lot_at(i: int, now: float) -> Variant:
	var k: Array = lot_keys[i]
	if now < float(k[0][0]) or now > float(k[k.size() - 1][0]):
		return null
	var c := cursor[i]
	if c > 0 and float(k[c][0]) > now:
		c = 0
	while c + 1 < k.size() and float(k[c + 1][0]) <= now:
		c += 1
	cursor[i] = c
	var a: Array = k[c]
	if c + 1 >= k.size():
		return [float(a[1]), float(a[2]), float(a[3])]
	var b: Array = k[c + 1]
	var span: float = float(b[0]) - float(a[0])
	var u: float = 0.0 if span <= 0.0 else (now - float(a[0])) / span
	return [lerpf(a[1], b[1], u), lerpf(a[2], b[2], u), lerpf(a[3], b[3], u)]


func _moving(i: int, now: float) -> bool:
	for m in lot_moves[i]:
		if now >= float(m[0]) and now <= float(m[1]):
			return true
	return false


var HIDE := Transform3D(Basis().scaled(Vector3.ZERO), Vector3(0, -50, 0))


func _place_lots() -> int:
	var shown := 0
	for i in lot_keys.size():
		var p = lot_at(i, t)
		var xf := HIDE
		lot_drawn[i] = p
		if p != null:
			xf = Transform3D(Basis(), w(p[0], p[1], p[2]))
			shown += 1
		var slot: Array = lot_slot[i]
		if slot[0] == null:
			hero_mi.transform = xf
		else:
			slot[0].set_instance_transform(slot[1], xf)
		if p != null and _moving(i, t):
			car_mm.set_instance_transform(i, Transform3D(Basis(), w(p[0], p[1], RAIL_Z)))
		else:
			car_mm.set_instance_transform(i, HIDE)
	return shown


func _lot_drawn(i: int) -> Array:
	var p: Array = lot_drawn[i]
	return plan(w(p[0], p[1], p[2]))


# ---------------------------------------------------------------------------- the player

func _player() -> void:
	player = CharacterBody3D.new()
	player.name = "player"
	player.collision_mask = 1
	player.collision_layer = 0
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.75
	cs.shape = cap
	cs.position = Vector3(0, 0.875, 0)
	player.add_child(cs)
	cam = Camera3D.new()
	cam.position = Vector3(0, 1.6, 0)
	cam.near = 0.05
	cam.far = 20000.0
	cam.fov = 62.0
	player.add_child(cam)
	add_child(player)


func _set_walk(on: bool) -> void:
	walking = on
	following = false
	vel_y = 0.0
	player.velocity = Vector3.ZERO
	if on:
		# drop to the clean floor below, if there is one; else walk the lithography bay
		var p := plan(player.global_position)
		if not _over_clean_floor(p[0], p[1]):
			view(2)
			return
		player.global_position = w(p[0], p[1], CZ + 0.02)
		cam.fov = 70.0
	else:
		cam.fov = 62.0


func _over_clean_floor(x: float, y: float) -> bool:
	for c in S["campus"]:
		if c["kind"] == "fab" and x > c["x0"] + 0.6 and x < c["x1"] - 0.6 and absf(y) < SP / 2 + DEPTH - 0.4:
			return true
	return false


func _first_bay(light: String, phase: int) -> Dictionary:
	for b in S["bays"]:
		if b["light"] == light and b["phase"] == phase:
			return b
	return S["bays"][0]


func view(n: int) -> void:
	following = false
	match n:
		1:
			walking = false
			player.global_position = w(40, -640, 230)
			_look(w(420, -40, 0))
			cam.fov = 50.0
		2:
			var b := _first_bay("yellow", 1)
			var cx: float = (b["x0"] + b["x1"]) / 2
			var sgn := 1.0 if b["side"] == 0 else -1.0
			walking = true
			player.global_position = w(cx, sgn * (SP / 2 + 3.0), CZ + 0.02)
			# face into the bay
			yaw = 0.0 if sgn > 0 else PI
			pitch = deg_to_rad(-4)
			cam.fov = 70.0
		3:
			walking = false
			following = hero >= 0
			cam.fov = 55.0
		4:
			walking = false
			_set_cut(true)
			var b := _first_bay("yellow", 1)
			var cx: float = (b["x0"] + b["x1"]) / 2
			player.global_position = w(cx - 40, -110, 75)
			_look(w(cx, 0, CZ))
			cam.fov = 50.0
	vel_y = 0.0
	player.velocity = Vector3.ZERO
	_aim()


func _look(target: Vector3) -> void:
	var d := target - (player.global_position + Vector3(0, 1.6, 0))
	yaw = atan2(-d.x, -d.z)
	pitch = atan2(d.y, Vector2(d.x, d.z).length())


func _aim() -> void:
	player.rotation = Vector3(0, yaw, 0)
	cam.rotation = Vector3(pitch, 0, 0)


func _set_cut(on: bool) -> void:
	cut = on
	for n in cut_nodes:
		n.visible = not on


func _inside() -> bool:
	if cut:
		return false
	var p := plan(cam.global_position)
	for c in S["campus"]:
		if c["kind"] == "fab" and p[0] > c["x0"] and p[0] < c["x1"] and p[1] > c["y0"] and p[1] < c["y1"] and p[2] < ROOF_TOP:
			return true
	return false


func _physics_process(delta: float) -> void:
	if S.is_empty():
		return
	if check_out != "":
		_check_step(delta)
		return
	var fwd := -player.global_transform.basis.z
	var right := player.global_transform.basis.x
	var move := Vector3.ZERO
	if Input.is_key_pressed(KEY_W):
		move += fwd
	if Input.is_key_pressed(KEY_S):
		move -= fwd
	if Input.is_key_pressed(KEY_D):
		move += right
	if Input.is_key_pressed(KEY_A):
		move -= right
	var fast := Input.is_key_pressed(KEY_SHIFT)
	if move != Vector3.ZERO:
		following = false
	if walking:
		move.y = 0
		_walk(move.normalized() * (3.5 if fast else 1.4), delta)
	else:
		var up := 0.0
		if Input.is_key_pressed(KEY_E):
			up += 1.0
		if Input.is_key_pressed(KEY_Q):
			up -= 1.0
		if up != 0.0:
			following = false
		var look := -cam.global_transform.basis.z
		var dir := Vector3.ZERO
		if Input.is_key_pressed(KEY_W):
			dir += look
		if Input.is_key_pressed(KEY_S):
			dir -= look
		if Input.is_key_pressed(KEY_D):
			dir += right
		if Input.is_key_pressed(KEY_A):
			dir -= right
		dir.y += up
		_fly(dir.normalized() * fly_speed * (6.0 if fast else 1.0), delta)


func _walk(v: Vector3, delta: float) -> void:
	if player.is_on_floor():
		vel_y = 0.0
	else:
		vel_y -= 9.81 * delta
	player.velocity = Vector3(v.x, vel_y, v.z)
	player.move_and_slide()


func _fly(v: Vector3, delta: float) -> void:
	player.global_position += v * delta
	if player.global_position.y < 0.3:
		player.global_position.y = 0.3


# ---------------------------------------------------------------------------- each frame

func _process(delta: float) -> void:
	if S.is_empty() or check_out != "":
		return
	if shot != "":
		shot_at -= delta
		if shot_at <= 0.0:
			get_viewport().get_texture().get_image().save_png(shot)
			get_tree().quit()
			return
	if not paused:
		t += delta * speed
		if t > float(S["to"]):
			t = float(S["from"])
			_reset_states()
	_apply_states_until(t)
	_place_lots()
	if following and hero >= 0:
		var p = lot_at(hero, t)
		if p != null:
			var target := w(p[0], p[1], p[2] + 0.2)
			var want := target + Vector3(-4.5, 2.2, 3.5)
			player.global_position = player.global_position.lerp(want - Vector3(0, 1.6, 0), clampf(delta * 2.5, 0, 1))
			var d := target - cam.global_position
			yaw = atan2(-d.x, -d.z)
			pitch = atan2(d.y, Vector2(d.x, d.z).length())
			_aim()
	var inside := _inside()
	sun.visible = not inside
	if inside:
		env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		env.ambient_light_color = Color("eef2f6")
		env.ambient_light_energy = 0.45
		env.fog_density = 0.0
	else:
		env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
		env.ambient_light_energy = 1.0
		env.fog_density = 0.00006
	var high := cam.global_position.y > 35.0
	for l in far_labels:
		l.visible = high
	var day := int(t / 1440.0)
	var hm := int(t) % 1440
	var counts := [0, 0, 0, 0]
	for s in tool_state:
		if s >= 0:
			counts[s] += 1
	var mode := "Walking" if walking else ("Following the film's lot" if following else "Flying")
	hud.text = "%s · simulated day %d, %02d:%02d  ×%d%s\nTools working %d · idle %d · maintenance %d · broken down %d" % [
		mode, day + 1, hm / 60, hm % 60, int(round(speed * 60.0)), "  (paused)" if paused else "",
		counts[0], counts[1], counts[2], counts[3]]


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseButton and e.pressed:
		if e.button_index == MOUSE_BUTTON_LEFT:
			if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
				Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
			else:
				_pick()
		elif e.button_index == MOUSE_BUTTON_WHEEL_UP and not walking:
			fly_speed = minf(fly_speed * 1.25, 400.0)
		elif e.button_index == MOUSE_BUTTON_WHEEL_DOWN and not walking:
			fly_speed = maxf(fly_speed / 1.25, 1.0)
	elif e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		following = false
		yaw -= e.relative.x * 0.0025
		pitch = clampf(pitch - e.relative.y * 0.0025, -1.5, 1.5)
		_aim()
	elif e is InputEventKey and e.pressed and not e.echo:
		match e.keycode:
			KEY_TAB:
				_set_walk(not walking)
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_SPACE:
				paused = not paused
			KEY_EQUAL, KEY_PLUS, KEY_KP_ADD:
				speed = minf(speed * 2.0, 64.0)
			KEY_MINUS, KEY_KP_SUBTRACT:
				speed = maxf(speed / 2.0, 1.0 / 16.0)
			KEY_C:
				_set_cut(not cut)
			KEY_H:
				help.visible = not help.visible
			KEY_1, KEY_2, KEY_3, KEY_4:
				if e.keycode != KEY_4:
					_set_cut(false)
				view(e.keycode - KEY_0)


func _pick() -> void:
	var from := cam.global_position
	var to := from - cam.global_transform.basis.z * 80.0
	var q := PhysicsRayQueryParameters3D.create(from, to, 2)
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		card_box.visible = false
		return
	var body: CollisionObject3D = hit["collider"]
	var owner_id := body.shape_find_owner(hit["shape"])
	var cs: Node = body.shape_owner_get_owner(owner_id)
	if not cs.has_meta("tool"):
		card_box.visible = false
		return
	var i: int = cs.get_meta("tool")
	var tl: Dictionary = S["tools"][i]
	var g: Dictionary = S["groups"][tl["g"]]
	var s := tool_state[i]
	card.text = "%s\n%s · %s\nPhase %d · %s" % [
		g["name"], S["areas"][g["area"]]["name"] if S["areas"].has(g["area"]) else g["area"],
		KIND_WORDS.get(tl["kind"], tl["kind"]), int(g["phase"]) + 1, STATE_WORDS[s] if s >= 0 else "idle"]
	card_box.visible = true


# ---------------------------------------------------------------------------- the screen

func _text(s: String, size: int, c: Color) -> Label:
	var l := Label.new()
	l.text = s
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", c)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	l.add_theme_constant_override("outline_size", 4)
	return l


func _panel() -> PanelContainer:
	var box := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.03, 0.05, 0.09, 0.72)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(14)
	box.add_theme_stylebox_override("panel", sb)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return box


func _hud() -> void:
	var cl := CanvasLayer.new()
	add_child(cl)
	var top := _panel()
	top.position = Vector2(24, 24)
	cl.add_child(top)
	var v := VBoxContainer.new()
	top.add_child(v)
	hud = _text("", 21, Color("e8eef7"))
	v.add_child(hud)
	help = _text(HELP, 15, Color("b8c4d6"))
	v.add_child(help)
	var badge := _text(BADGE, 17, Color("dfe6ef"))
	cl.add_child(badge)
	badge.anchor_top = 1.0
	badge.anchor_bottom = 1.0
	badge.offset_left = 26
	badge.offset_top = -46
	badge.offset_bottom = -20
	card_box = _panel()
	card_box.visible = false
	cl.add_child(card_box)
	card_box.anchor_left = 1.0
	card_box.anchor_right = 1.0
	card_box.anchor_top = 1.0
	card_box.anchor_bottom = 1.0
	card_box.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	card_box.grow_vertical = Control.GROW_DIRECTION_BEGIN
	card_box.offset_right = -24
	card_box.offset_bottom = -24
	card = _text("", 19, Color("f4f7fb"))
	card_box.add_child(card)
	cross = ColorRect.new()
	cross.color = Color(1, 1, 1, 0.7)
	cross.size = Vector2(4, 4)
	cross.position = Vector2(958, 538)
	cross.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cl.add_child(cross)


# ---------------------------------------------------------------------------- the headless check

func _check_start() -> void:
	check["t"] = t
	check["tools"] = S["tools"].size()
	var per := {}
	var surfaces := {}
	for k in body_mm:
		per[k] = body_mm[k].instance_count
		surfaces[k] = body_mm[k].mesh.get_surface_count()
	for k in M["kinds"]:
		if not surfaces.has(k):
			surfaces[k] = parts_mesh(M["kinds"][k], false).get_surface_count()
	check["per_kind"] = per
	check["surfaces"] = surfaces
	var lamps: Array = []
	for i in tool_state.size():
		lamps.append(lamp_set[i])
	check["lamps"] = lamps
	var shown := _place_lots()
	check["lots_visible"] = shown
	var samples: Array = []
	for i in lot_keys.size():
		if lot_at(i, t) != null:
			var p := _lot_drawn(i)
			samples.append([i, p[0], p[1], p[2]])
			if samples.size() >= 40:
				break
	check["lot_samples"] = samples
	check["badge"] = BADGE
	# walk at the front of the first tool of the first bay, toward it
	var i0 := 0
	var tl: Dictionary = S["tools"][i0]
	var b: Dictionary = S["bays"][tl["bay"]]
	var ax: float = (b["x0"] + b["x1"]) / 2
	var cy: float = (tl["y0"] + tl["y1"]) / 2
	walking = true
	player.global_position = w(ax, cy, CZ + 0.02)
	script_dir = Vector3(-1, 0, 0) if tl["wall"] == 0 else Vector3(1, 0, 0)
	check["walk"] = {"tool": i0, "start": plan(cam.global_position)}
	check_phase = 1
	check_frames = 0


func _check_step(delta: float) -> void:
	check_frames += 1
	if check_phase == 1:
		_walk(script_dir * 1.4, delta)
		if check_frames >= 240:
			check["walk"]["end"] = plan(cam.global_position)
			check["walk"]["eye"] = cam.global_position.y
			walking = false
			var st: Array = check["walk"]["start"]
			player.global_position = w(st[0], st[1], st[2] - 1.6)
			check["fly"] = {"start": plan(cam.global_position)}
			check_phase = 2
			check_frames = 0
	elif check_phase == 2:
		_fly(script_dir * 6.0, delta)
		if check_frames >= 180:
			check["fly"]["end"] = plan(cam.global_position)
			var f := FileAccess.open(check_out, FileAccess.WRITE)
			f.store_string(JSON.stringify(check, " "))
			f.close()
			print("check written: ", check_out)
			check_phase = 3
			get_tree().quit()
