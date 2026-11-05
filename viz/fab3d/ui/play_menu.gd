extends CanvasLayer
## First launch, pause, travel and comfort controls share one keyboard-accessible menu.

var world: Node
var panel: Control
var heading: Label
var resume_button: Button
var status: Label
var welcome := true
var reduced_motion := false
var sensitivity := 1.0
var inverted := false
var reverse_trackpad := false
var settings_path := "user://visitor.cfg"
var _return_focus: Control


func _ready() -> void:
	layer = 20
	process_mode = Node.PROCESS_MODE_ALWAYS
	if "--playability-check" in OS.get_cmdline_user_args():
		settings_path = ""
	_load_settings()
	panel = ColorRect.new()
	panel.color = Color(0.025, 0.035, 0.08, 0.94)
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(panel)
	var centre := CenterContainer.new()
	centre.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.add_child(centre)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(760, 850)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	centre.add_child(scroll)
	var box := VBoxContainer.new()
	box.custom_minimum_size.x = 720
	box.add_theme_constant_override("separation", 12)
	box.add_theme_font_size_override("font_size", 24)
	scroll.add_child(box)
	heading = _label(box, "Welcome to Fab Gym", 42)
	_label(box, "Explore a simulated chip factory with Lou, your guide.", 23)
	status = _label(box, "Tour and explore freely. Live data connects when available.", 21)
	status.modulate = Color(0.7, 0.82, 0.95)
	resume_button = _button(box, "Resume", close)
	_button(box, "Take the guided tour", func() -> void: close(); world.choose_view("tour"))
	var views := HBoxContainer.new()
	views.add_theme_constant_override("separation", 12)
	box.add_child(views)
	_button(views, "Walk and explore", func() -> void: close(); world.choose_view("walk"))
	_button(views, "Fly over the fab", func() -> void: close(); world.choose_view("fly"))
	var travel := HBoxContainer.new()
	travel.add_theme_constant_override("separation", 12)
	box.add_child(travel)
	var places := OptionButton.new()
	for place in ["Parking lot", "Phase one", "Bridge", "Phase two", "Cinema"]:
		places.add_item(place)
	places.add_theme_font_size_override("font_size", 24)
	places.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	places.custom_minimum_size.y = 50
	travel.add_child(places)
	_button(travel, "Go to place", func() -> void: close(); world.travel_to(places.get_item_text(places.selected)))
	_label(box, "Move  W A S D / arrows    Look  two-finger trackpad swipe\nM  one-finger look on / off    Right-drag / I J K L also look\nShift  move faster    F  fly / land    E / Q  fly up / down\nMap: blue arrow is you; Campus shows all places. Go travels there.\nEsc  pause    Cinema: E sit / stand, Enter play, Space pause", 21)
	_label(box, "Controller: left stick move, right stick look, X fly, bumpers rise / descend.\nA interact, Y next / play, Start menu. Tab / arrows navigate buttons.", 19)
	var row := HBoxContainer.new()
	box.add_child(row)
	_label(row, "Look sensitivity", 22)
	var slider := HSlider.new()
	slider.min_value = 0.3
	slider.max_value = 2.0
	slider.step = 0.1
	slider.value = sensitivity
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.tooltip_text = "Trackpad, mouse and controller look sensitivity"
	row.add_child(slider)
	slider.value_changed.connect(func(v: float) -> void: sensitivity = v; apply_settings(); _save_settings())
	var invert := CheckButton.new()
	invert.text = "Invert vertical look"
	invert.add_theme_font_size_override("font_size", 22)
	invert.button_pressed = inverted
	box.add_child(invert)
	invert.toggled.connect(func(on: bool) -> void: inverted = on; apply_settings(); _save_settings())
	var trackpad := CheckButton.new()
	trackpad.text = "Reverse two-finger swipe direction"
	trackpad.add_theme_font_size_override("font_size", 22)
	trackpad.button_pressed = reverse_trackpad
	box.add_child(trackpad)
	trackpad.toggled.connect(func(on: bool) -> void: reverse_trackpad = on; apply_settings(); _save_settings())
	var motion := CheckButton.new()
	motion.text = "Reduce camera motion (skip opening flight)"
	motion.add_theme_font_size_override("font_size", 22)
	motion.button_pressed = reduced_motion
	box.add_child(motion)
	motion.toggled.connect(func(on: bool) -> void: reduced_motion = on; apply_settings(); _save_settings())
	var bottom := HBoxContainer.new()
	bottom.add_theme_constant_override("separation", 12)
	box.add_child(bottom)
	_button(bottom, "Full screen / window", func() -> void:
		var full := DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if full else DisplayServer.WINDOW_MODE_FULLSCREEN))
	_button(bottom, "Reconnect live data", func() -> void: world.live.start())
	if not OS.has_feature("web"):
		_button(bottom, "Quit", func() -> void: get_tree().quit())
	_label(box, "SMT2020 testbed · our own layout · not a real fab", 18)
	get_viewport().size_changed.connect(func() -> void:
		var size := get_viewport().get_visible_rect().size
		scroll.custom_minimum_size = Vector2(minf(760, size.x - 40), minf(920, size.y - 40))
		box.custom_minimum_size.x = minf(720, size.x - 80))
	get_viewport().size_changed.emit()
	panel.hide()


func _label(parent: Node, text: String, size: int) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(l)
	return l


func _button(parent: Node, text: String, callback: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", 24)
	b.custom_minimum_size.y = 52
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.pressed.connect(callback)
	parent.add_child(b)
	return b


func is_open() -> bool:
	return panel != null and panel.visible


func open(first := false) -> void:
	welcome = first
	heading.text = "Welcome to Fab Gym" if first else "Visit paused"
	resume_button.visible = not first
	_return_focus = get_viewport().gui_get_focus_owner()
	world.player.release_look()
	panel.show()
	get_tree().paused = true
	if first:
		resume_button.get_parent().get_child(resume_button.get_index() + 1).grab_focus()
	else:
		resume_button.grab_focus()


func close() -> void:
	panel.hide()
	var focus := get_viewport().gui_get_focus_owner()
	if focus:
		focus.release_focus()
	get_tree().paused = false
	welcome = false


func _input(e: InputEvent) -> void:
	if e.is_action_pressed("visit_menu"):
		# A film owns Escape until the visitor has returned to the hall.
		if world.cinema.full.visible:
			return
		if is_open():
			if not welcome:
				close()
		elif world.ui.ask_panel.visible or world.ui.card.visible:
			return
		else:
			open()
		get_viewport().set_input_as_handled()


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT and is_instance_valid(world) and not is_open():
		if DisplayServer.get_name() != "headless" and not world.automated and not "--playability-check" in OS.get_cmdline_user_args():
			if world.cinema.full.visible:
				world.cinema.user_paused = true
				world.cinema.video.paused = true
			else:
				open()


func apply_settings() -> void:
	world.player.look_sensitivity = sensitivity
	world.player.invert_look = inverted
	world.player.reverse_trackpad = reverse_trackpad
	world.player.reduced_motion = reduced_motion


func _load_settings() -> void:
	var config := ConfigFile.new()
	if settings_path != "" and config.load(settings_path) == OK:
		sensitivity = clampf(float(config.get_value("view", "sensitivity", 1.0)), 0.3, 2.0)
		inverted = bool(config.get_value("view", "inverted", false))
		reverse_trackpad = bool(config.get_value("view", "reverse_trackpad", false))
		reduced_motion = bool(config.get_value("view", "reduced_motion", false))


func _save_settings() -> void:
	if settings_path == "":
		return
	var config := ConfigFile.new()
	config.set_value("view", "sensitivity", sensitivity)
	config.set_value("view", "inverted", inverted)
	config.set_value("view", "reverse_trackpad", reverse_trackpad)
	config.set_value("view", "reduced_motion", reduced_motion)
	config.save(settings_path)
