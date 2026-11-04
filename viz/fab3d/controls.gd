extends RefCounted
## Physical movement keys work across keyboard layouts. Arrows and I/J/K/L allow mouse-free play.

static func setup() -> void:
	var keys := {
		"walk_forward": [KEY_W, KEY_UP], "walk_back": [KEY_S, KEY_DOWN],
		"walk_left": [KEY_A, KEY_LEFT], "walk_right": [KEY_D, KEY_RIGHT],
		"look_left": [KEY_J], "look_right": [KEY_L], "look_up": [KEY_I], "look_down": [KEY_K],
		"hurry": [KEY_SHIFT], "fly_up": [KEY_E, KEY_PAGEUP], "fly_down": [KEY_Q, KEY_PAGEDOWN],
		"toggle_flight": [KEY_F], "toggle_look": [KEY_M], "interact": [KEY_E],
		"visit_menu": [KEY_ESCAPE], "next_line": [KEY_SPACE], "movie_play": [KEY_ENTER, KEY_KP_ENTER]
	}
	for action in keys:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action, 0.2)
		for code in keys[action]:
			var e := InputEventKey.new()
			e.physical_keycode = code
			InputMap.action_add_event(action, e)
	for spec in [["walk_left", JOY_AXIS_LEFT_X, -1.0], ["walk_right", JOY_AXIS_LEFT_X, 1.0],
			["walk_forward", JOY_AXIS_LEFT_Y, -1.0], ["walk_back", JOY_AXIS_LEFT_Y, 1.0],
			["look_left", JOY_AXIS_RIGHT_X, -1.0], ["look_right", JOY_AXIS_RIGHT_X, 1.0],
			["look_up", JOY_AXIS_RIGHT_Y, -1.0], ["look_down", JOY_AXIS_RIGHT_Y, 1.0]]:
		var e := InputEventJoypadMotion.new()
		e.axis = spec[1]
		e.axis_value = spec[2]
		if not InputMap.action_has_event(spec[0], e):
			InputMap.action_add_event(spec[0], e)
	for spec in [["visit_menu", JOY_BUTTON_START], ["interact", JOY_BUTTON_A],
			["toggle_flight", JOY_BUTTON_X], ["fly_up", JOY_BUTTON_RIGHT_SHOULDER],
			["fly_down", JOY_BUTTON_LEFT_SHOULDER], ["hurry", JOY_BUTTON_LEFT_STICK],
			["next_line", JOY_BUTTON_Y], ["movie_play", JOY_BUTTON_Y]]:
		var e := InputEventJoypadButton.new()
		e.button_index = spec[1]
		if not InputMap.action_has_event(spec[0], e):
			InputMap.action_add_event(spec[0], e)
