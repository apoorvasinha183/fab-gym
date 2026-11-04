extends CanvasLayer
## The screen (docs/FAB-3D.md), in the look chosen 2 Nov (a JRPG dialogue): a menu window, a status window with the
## clock and the stop, the CEO's portrait beside a text window whose line types out and ends with a bobbing arrow,
## an ask window with a microphone button, and a card for the tool you click. Space or a click on the text window
## finishes the line, then moves on. A spoken question is recorded here (at most 30 seconds), packed as WAV and sent
## to the helper, which has Meta's speech model write it down. From the SMT2020 testbed; not a real fab.

signal asked(text: String)
signal recorded(wav: PackedByteArray)
signal speed_changed(minutes_a_second: float)
signal free_walk
signal menu_requested
signal advance                      # the visitor wants the next line

const MAX_SECONDS := 30.0
const TYPE_RATE := 48.0             # characters a second as a line types out
const SPEEDS := [[1.0 / 60.0, "REAL TIME"], [10.0 / 60.0, "10X"], [1.0, "60X"]]

@onready var clock_label: Label = $root/status/list/clock
@onready var stop_label: Label = $root/status/list/stop
@onready var line_label: RichTextLabel = $root/talk/box/line
@onready var next_mark: Polygon2D = $root/talk/next
@onready var ask_panel: PanelContainer = $root/ask
@onready var ask_box: LineEdit = $root/ask/row/box
@onready var mic: Button = $root/ask/row/mic
@onready var card: PanelContainer = $root/card
@onready var card_text: RichTextLabel = $root/card/text
@onready var hint: Label = $root/hint
@onready var speed_button: Button = $root/menu/list/speed
@onready var prompt_panel: PanelContainer = $root/prompt
@onready var prompt_label: Label = $root/prompt/text

var recording := false
var _bus := -1
var _capture: AudioEffectCapture
var _player: AudioStreamPlayer
var _frames := PackedVector2Array()
var _seconds := 0.0
var _typed := 0.0
var _speed_i := 0
var _bob := 0.0
var talking := true                 # set by the scene: the CEO is speaking; when not, the text window closes
var _done_for := 0.0                # seconds since the current line finished typing


func _ready() -> void:
	ask_box.text_submitted.connect(func(t: String) -> void:
		if t.strip_edges() != "":
			asked.emit(t.strip_edges())
			ask_box.text = ""
			ask_box.release_focus())
	mic.pressed.connect(_toggle_mic)
	$root/menu/list/ask.pressed.connect(func() -> void:
		ask_panel.visible = not ask_panel.visible
		if ask_panel.visible:
			ask_box.grab_focus())
	$root/menu/list/free.pressed.connect(func() -> void:
		$root/menu/list/free.release_focus()
		free_walk.emit())
	speed_button.pressed.connect(func() -> void:
		speed_button.release_focus()
		_speed_i = (_speed_i + 1) % SPEEDS.size()
		speed_button.text = "SPEED  " + str(SPEEDS[_speed_i][1])
		speed_changed.emit(float(SPEEDS[_speed_i][0])))
	$root/talk.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT:
			_next())
	var menu_button := Button.new()
	menu_button.text = "PAUSE / PLACES"
	menu_button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	$root/menu/list.add_child(menu_button)
	menu_button.pressed.connect(func() -> void: menu_requested.emit())
	card.visible = false
	next_mark.visible = false


func _input(e: InputEvent) -> void:
	if e is InputEventKey and e.pressed and not e.echo and e.keycode == KEY_ESCAPE:
		if ask_panel.visible:
			ask_box.release_focus()
			ask_panel.hide()
			get_viewport().set_input_as_handled()
		elif card.visible:
			card.hide()
			get_viewport().set_input_as_handled()


func _unhandled_input(e: InputEvent) -> void:
	if e.is_action_pressed("next_line") and not e.is_echo():
		_next()
		get_viewport().set_input_as_handled()


func _next() -> void:
	# first finish typing the line, then ask for the next one
	if line_label.visible_ratio < 1.0:
		line_label.visible_ratio = 1.0
		_typed = 1e9
	else:
		advance.emit()


func show_line(text: String) -> void:
	line_label.text = text
	if text.is_empty():
		line_label.visible_characters = -1
		_done_for = 100.0
		$root/talk.hide()
		$root/face.hide()
		return
	line_label.visible_characters = 0
	_typed = 0.0
	_done_for = 0.0
	next_mark.visible = false


func show_prompt(text: String) -> void:
	# what the keys do here (the cinema's seats and film); empty hides it
	prompt_label.text = text
	prompt_panel.visible = text != ""


func set_stop(n: int, total: int, title: String) -> void:
	stop_label.text = ("STOP %d / %d  %s" % [n, total, title]).to_upper() if n > 0 else title.to_upper()


func show_card(text: String) -> void:
	card_text.text = text
	card.visible = text != ""


func set_clock(minutes: float, speed: float) -> void:
	var day := int(minutes / 1440.0) + 1
	var m := int(minutes) % 1440
	clock_label.text = "DAY %d   %02d:%02d:%02d" % [day, m / 60, m % 60, int(minutes * 60.0) % 60]


# ------------------------------------------------------------------ the microphone

func _toggle_mic() -> void:
	if recording:
		_stop()
	else:
		_start()


func _start() -> void:
	if _bus < 0:
		_bus = AudioServer.bus_count
		AudioServer.add_bus(_bus)
		AudioServer.set_bus_name(_bus, "Question")
		AudioServer.set_bus_mute(_bus, true)
		_capture = AudioEffectCapture.new()
		AudioServer.add_bus_effect(_bus, _capture)
		_player = AudioStreamPlayer.new()
		_player.stream = AudioStreamMicrophone.new()
		_player.bus = "Question"
		add_child(_player)
	_frames = PackedVector2Array()
	_seconds = 0.0
	_capture.clear_buffer()
	_player.play()
	recording = true
	mic.text = "STOP"
	hint.text = "LISTENING... ASK YOUR QUESTION, THEN PRESS STOP"


func _stop() -> void:
	recording = false
	_player.stop()
	mic.text = "SPEAK"
	hint.text = "WRITING DOWN WHAT YOU SAID..."
	recorded.emit(_wav(_frames, int(AudioServer.get_mix_rate())))


func _process(dt: float) -> void:
	var total := line_label.get_total_character_count()
	if line_label.visible_characters >= 0 and line_label.visible_characters < total:
		_typed += dt * TYPE_RATE
		line_label.visible_characters = mini(int(_typed), total)
		if line_label.visible_characters >= total:
			line_label.visible_characters = -1
	next_mark.visible = line_label.visible_characters < 0
	if next_mark.visible:
		_done_for += dt
	# the text window and portrait stay while the CEO talks or a line was just written, then fade out
	var show := talking or line_label.visible_characters >= 0 or _done_for < maxf(2.5, total / 20.0)
	for w in [$root/talk, $root/face]:
		w.modulate.a = move_toward(w.modulate.a, 1.0 if show else 0.0, dt * 4.0)
		w.visible = w.modulate.a > 0.01
	if next_mark.visible:
		_bob += dt * 5.0
		var box: Vector2 = next_mark.get_parent().size
		next_mark.position = Vector2(box.x - 44.0, box.y - 40.0 + sin(_bob) * 4.0)
	if recording:
		_seconds += dt
		var n := _capture.get_frames_available()
		if n > 0:
			_frames.append_array(_capture.get_buffer(n))
		if _seconds >= MAX_SECONDS:
			_stop()


static func _wav(frames: PackedVector2Array, rate: int) -> PackedByteArray:
	# 16-bit mono PCM in a WAV file
	var pcm := PackedByteArray()
	pcm.resize(frames.size() * 2)
	for k in frames.size():
		var s := int(clampf((frames[k].x + frames[k].y) * 0.5, -1.0, 1.0) * 32767.0)
		pcm.encode_s16(k * 2, s)
	var h := PackedByteArray()
	h.resize(44)
	h.encode_u32(0, 0x46464952)        # RIFF
	h.encode_u32(4, 36 + pcm.size())
	h.encode_u32(8, 0x45564157)        # WAVE
	h.encode_u32(12, 0x20746d66)       # fmt
	h.encode_u32(16, 16)
	h.encode_u16(20, 1)
	h.encode_u16(22, 1)
	h.encode_u32(24, rate)
	h.encode_u32(28, rate * 2)
	h.encode_u16(32, 2)
	h.encode_u16(34, 16)
	h.encode_u32(36, 0x61746164)       # data
	h.encode_u32(40, pcm.size())
	return h + pcm
