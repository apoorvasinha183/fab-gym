extends RefCounted
## Materials from the CC0 texture sets (Poly Haven, in data/textures; docs/FAB-3D.md): colour, normal and packed
## AO-roughness-metal (or roughness) maps, mapped by world position so a surface of any size tiles evenly at the size
## given. `dress` swaps a model's materials by name. From the SMT2020 testbed; not a real fab.

static var _cache := {}


static func pbr(asset: String, metres: float, tint := Color(1, 1, 1), metallic := -1.0, colour := "diff", lite := false) -> StandardMaterial3D:
	# colour picks the colour map: "diff", or "grey" for a greyed copy that the tint colours. lite, for surfaces that
	# fill the screen (ground, roofs, roads): colour, normal and roughness only, no AO or metal map (each map is read
	# three times by the world projection, so this saves about 40% of the texture reads)
	var key := "%s|%s|%s|%s|%s|%s" % [asset, metres, tint, metallic, colour, lite]
	if _cache.has(key):
		return _cache[key]
	var base := "res://data/textures/%s/%s_" % [asset, asset]
	var m := StandardMaterial3D.new()
	m.resource_name = asset
	if ResourceLoader.exists(base + colour + "_1k.jpg"):
		m.albedo_texture = load(base + colour + "_1k.jpg")
	m.albedo_color = tint
	if ResourceLoader.exists(base + "nor_gl_1k.jpg"):
		m.normal_enabled = true
		m.normal_scale = 0.65 if lite else 1.0
		m.normal_texture = load(base + "nor_gl_1k.jpg")
	if lite and ResourceLoader.exists(base + "arm_1k.jpg"):
		m.roughness_texture = load(base + "arm_1k.jpg")
		m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		m.roughness = 1.0
		m.metallic = 0.0
	elif ResourceLoader.exists(base + "arm_1k.jpg"):
		var arm: Texture2D = load(base + "arm_1k.jpg")
		m.ao_enabled = true
		m.ao_texture = arm
		m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
		m.roughness_texture = arm
		m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		m.roughness = 1.0
		m.metallic_texture = arm
		m.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE
		m.metallic = 1.0
	elif ResourceLoader.exists(base + "rough_1k.jpg"):
		m.roughness_texture = load(base + "rough_1k.jpg")
		m.roughness = 1.0
	if metallic >= 0.0 and not lite:
		m.metallic_texture = null
		m.metallic = metallic
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3.ONE / metres
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	_cache[key] = m
	return m


static func dress(node: Node, by_name: Dictionary) -> int:
	# every surface whose material is named in by_name gets that material instead; returns how many were swapped
	var n := 0
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		for k in mi.mesh.get_surface_count():
			var m: Material = mi.mesh.surface_get_material(k)
			if m and by_name.has(m.resource_name):
				mi.set_surface_override_material(k, by_name[m.resource_name])
				n += 1
	return n
