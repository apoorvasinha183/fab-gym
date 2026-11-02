extends Node3D
## The campus cinema (docs/FAB-3D.md): the silicon film, "From sand to chip", plays on the hall's screen while the
## visitor is in the hall and pauses when they leave. The film is ours, converted to Ogg Theora (the video format Godot
## plays). From the SMT2020 testbed; not a real fab.

const FILM := "res://data/film/from-sand-to-chip.ogv"
const HALL := Rect2(40.3, -121.7, 35.4, 16.4)     # plan x, y, width, depth of the hall (cinema.py)

var viewer: Node3D
var video: VideoStreamPlayer
var started := false


func _ready() -> void:
	var vp := SubViewport.new()
	vp.size = Vector2i(1280, 720)
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(vp)
	video = VideoStreamPlayer.new()
	if ResourceLoader.exists(FILM):
		video.stream = load(FILM)
	video.size = Vector2(1280, 720)
	video.expand = true
	vp.add_child(video)
	var screen := _find(self, "screen")
	if screen:
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.albedo_texture = vp.get_texture()
		screen.material_override = m


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


func in_hall(p: Vector3) -> bool:
	return HALL.has_point(Vector2(p.x, -p.z))


func _process(_dt: float) -> void:
	if not viewer or not video.stream:
		return
	var inside := in_hall(viewer.global_position)
	if inside and not started:
		video.play()
		started = true
	elif started:
		video.paused = not inside
