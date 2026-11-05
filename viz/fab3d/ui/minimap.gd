extends CanvasLayer
## North-up floor plan, shared by walking, flying and the guided tour.
## Plan coordinates are (world.x, -world.z); no second copy of the campus geometry.

const YOU := Color("79d9ff")
const LOU := Color("ffd166")
const INK := Color("e4edff")
var world: Node
var panel: PanelContainer
var drawing: Control
var location: Label
var overview_button: Button
var look_button: Button
var places: OptionButton
var overview := false
var centre := Vector2.ZERO
var pixels_per_metre := 1.0
var _tick := 0.0


class MapDrawing extends Control:
	var navigation: CanvasLayer
	func _draw() -> void:
		navigation.draw_map(self)


func _ready() -> void:
	layer = 4
	process_mode = Node.PROCESS_MODE_ALWAYS
	panel = PanelContainer.new()
	panel.name = "VisitorMap"
	panel.theme = preload("res://ui/jrpg.tres")
	panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	panel.offset_left = -438
	panel.offset_right = -28
	panel.offset_top = 192
	panel.mouse_force_pass_scroll_events = false
	panel.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventPanGesture or e is InputEventMouseButton:
			panel.accept_event())
	add_child(panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	panel.add_child(box)
	var top := HBoxContainer.new()
	box.add_child(top)
	var title := _label(top, "YOU ARE HERE", 21)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.modulate = LOU
	overview_button = _button(top, "Campus", toggle_overview)
	overview_button.tooltip_text = "Switch between the whole campus and your nearby floor plan"
	drawing = MapDrawing.new()
	drawing.navigation = self
	drawing.custom_minimum_size = Vector2(370, 200)
	drawing.clip_contents = true
	# Scrolling over the map belongs to this panel, never to the camera behind it.
	drawing.mouse_filter = Control.MOUSE_FILTER_STOP
	drawing.mouse_force_pass_scroll_events = false
	drawing.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventPanGesture or e is InputEventMouseButton:
			drawing.accept_event())
	box.add_child(drawing)
	location = _label(box, "", 18)
	location.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	location.custom_minimum_size.y = 48
	var travel := HBoxContainer.new()
	box.add_child(travel)
	places = OptionButton.new()
	places.add_theme_font_size_override("font_size", 20)
	places.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	for place in ["Parking lot", "Phase one", "Bridge", "Phase two", "Cinema"]:
		places.add_item(place)
	places.selected = 1
	travel.add_child(places)
	_button(travel, "Go", func() -> void:
		world.travel_to(places.get_item_text(places.selected)))
	look_button = _button(world.ui.get_node("root/menu/list"), "M  TRACKPAD LOOK", func() -> void: world.player.toggle_mouse_look())
	look_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	look_button.tooltip_text = "Move one finger to look around; press M again to release the pointer"
	_process(0.0)


func _label(parent: Node, text: String, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	parent.add_child(label)
	return label


func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.add_theme_font_size_override("font_size", 20)
	button.custom_minimum_size.y = 38
	button.pressed.connect(func() -> void: button.release_focus(); callback.call())
	parent.add_child(button)
	return button


func toggle_overview() -> void:
	overview = not overview
	overview_button.text = "Nearby" if overview else "Campus"
	update_transform()
	drawing.queue_redraw()


func _process(dt: float) -> void:
	panel.visible = world.ui.visible and not world.play_menu.is_open() and not world.cinema.full.visible and not world.ui.card.visible and not world.ui.ask_panel.visible
	look_button.disabled = not world.player.roaming or world.player.input_locked
	look_button.text = "M  STOP LOOKING" if world.player.mouse_look_active() else "M  TRACKPAD LOOK"
	if not panel.visible:
		return
	_tick += dt
	if _tick < 0.05:
		return
	_tick = 0.0
	update_transform()
	location.text = location_text()
	drawing.queue_redraw()


func player_plan() -> Vector2:
	return Vector2(world.player.global_position.x, -world.player.global_position.z)


func update_transform() -> void:
	centre = player_plan()
	pixels_per_metre = drawing.size.x / 140.0
	if overview:
		var bounds := Rect2(centre, Vector2.ZERO)
		for f in world.campus.data["fabs"]:
			bounds = bounds.expand(Vector2(float(f[0]), float(f[2])))
			bounds = bounds.expand(Vector2(float(f[1]), float(f[3])))
		for at in landmarks().values():
			bounds = bounds.expand(at)
		var hall: Array = world.campus.data["cinema"]["hall"]
		bounds = bounds.expand(Vector2(float(hall[0]), float(hall[1])))
		bounds = bounds.grow(32.0)
		centre = bounds.get_center()
		pixels_per_metre = minf(drawing.size.x / bounds.size.x, drawing.size.y / bounds.size.y)


func plan_to_map(at: Vector2) -> Vector2:
	var d := (at - centre) * pixels_per_metre
	return drawing.size * 0.5 + Vector2(d.x, -d.y)


func heading_vector() -> Vector2:
	return Vector2(-sin(world.player.yaw), -cos(world.player.yaw))


func landmarks() -> Dictionary:
	var lot: Array = world.campus.data["entrance"]["route"][0]["at"]
	var lift: Array = world.campus.data["entrance"]["permit"]["lift"]["box"]
	return {"Parking": Vector2(float(lot[0]), float(lot[1])),
		"Lift": Vector2((float(lift[0]) + float(lift[3])) * 0.5, (float(lift[1]) + float(lift[4])) * 0.5),
		"Cinema": Vector2(58, -104)}


func location_text() -> String:
	var at := player_plan()
	var where := "Campus grounds"
	for f in world.campus.data["fabs"]:
		if at.x >= float(f[0]) and at.x <= float(f[1]) and at.y >= float(f[2]) and at.y <= float(f[3]):
			where = str(f[4])
			break
	if world.player.in_cinema(at.x, at.y):
		where = "Cinema"
	elif at.distance_to(landmarks()["Parking"]) < 25.0:
		where = "Parking lot"
	var mode: String = "Flying" if world.player.fly else ("With Lou" if not world.player.roaming else "Walking")
	return "%s · %s\nBlue: you   Gold: Lou" % [where, mode]


func _box(canvas: Control, x0: float, x1: float, y0: float, y1: float, colour: Color) -> void:
	var a := plan_to_map(Vector2(x0, y1))
	var b := plan_to_map(Vector2(x1, y0))
	var rect := Rect2(a, b - a)
	if not rect.intersects(Rect2(Vector2.ZERO, drawing.size)):
		return
	canvas.draw_rect(rect, colour)
	canvas.draw_rect(rect, Color("69829f"), false, 1.0)


func _text(canvas: Control, at: Vector2, text: String, colour := INK, font_size := 16) -> void:
	var font := ThemeDB.fallback_font
	var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	var point := Vector2(clampf(at.x, 5, drawing.size.x - width - 5), clampf(at.y, font_size + 3, drawing.size.y - 6))
	canvas.draw_string_outline(font, point, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, 4, Color("0d192a"))
	canvas.draw_string(font, point, text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, colour)


func draw_map(canvas: Control) -> void:
	canvas.draw_rect(Rect2(Vector2.ZERO, drawing.size), Color("101e30"))
	for f in world.campus.data["fabs"]:
		_box(canvas, float(f[0]), float(f[1]), float(f[2]), float(f[3]), Color("263e50"))
	if not overview:
		for bay in world.campus.data["bays"]:
			_box(canvas, float(bay[0]), float(bay[1]), float(bay[2]), float(bay[3]), Color("3d5267"))
		# The empty central spine and the bay divisions are the navigation cues.
		for label in world.campus.data["labels"]:
			var at := plan_to_map(Vector2(float(label[1]), float(label[2])))
			if Rect2(Vector2(20, 20), drawing.size - Vector2(55, 40)).has_point(at):
				_text(canvas, at, str(label[3]), Color("b2c5da"), 14)
	var hall: Array = world.campus.data["cinema"]["hall"]
	_box(canvas, float(hall[0]), float(hall[2]), float(hall[1]), float(hall[3]), Color("69536e"))
	for name in landmarks():
		if overview and name == "Lift":
			continue
		var at := plan_to_map(landmarks()[name])
		if Rect2(Vector2.ZERO, drawing.size).has_point(at):
			canvas.draw_circle(at, 4, INK)
			_text(canvas, at + Vector2(7, -7), name)
	if overview:
		_text(canvas, plan_to_map(Vector2(70, 20)), "Phase 1")
		_text(canvas, plan_to_map(Vector2(366, 20)), "Phase 2")
		_text(canvas, plan_to_map(Vector2(263, -25)), "Bridge")
	var guide: Vector3 = world.guide.global_position
	var guide_at := plan_to_map(Vector2(guide.x, -guide.z))
	if world.guide.visible and Rect2(Vector2.ZERO, drawing.size).has_point(guide_at):
		canvas.draw_circle(guide_at, 6, LOU)
		if not overview:
			_text(canvas, guide_at + Vector2(9, 0), "Lou", LOU)
	var you := plan_to_map(player_plan())
	var forward := heading_vector()
	var side := Vector2(-forward.y, forward.x)
	canvas.draw_circle(you, 14, Color(0.01, 0.07, 0.13, 0.8))
	canvas.draw_colored_polygon(PackedVector2Array([you + forward * 12, you - forward * 8 + side * 8, you - forward * 4, you - forward * 8 - side * 8]), YOU)
	_text(canvas, Vector2(drawing.size.x - 22, 20), "N", INK, 18)
	var metres := 100.0 if overview else 20.0
	var origin := Vector2(12, drawing.size.y - 14)
	canvas.draw_line(origin, origin + Vector2(metres * pixels_per_metre, 0), INK, 2.0)
	_text(canvas, origin + Vector2(0, -6), "%d m" % int(metres), INK, 14)
