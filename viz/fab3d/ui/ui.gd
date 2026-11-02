extends CanvasLayer
## The panel (docs/FAB-3D.md): the clock and speed, the ask box with a microphone button, the guide's last line, and a
## card for the tool you click. A spoken question is recorded here (at most 30 seconds), packed as WAV and sent to the
## helper, which has Meta's speech model write it down. From the SMT2020 testbed; not a real fab.

signal asked(text: String)
signal recorded(wav: PackedByteArray)
signal speed_changed(minutes_a_second: float)
signal free_walk

const MAX_SECONDS := 30.0

@onready var clock_label: Label = $clock
@onready var line_label: RichTextLabel = $talk/line
@onready var ask_box: LineEdit = $ask/box
@onready var mic: Button = $ask/mic
@onready var card: PanelContainer = $card
@onready var card_text: RichTextLabel = $card/text
@onready var hint: Label = $hint

var recording := false
var _bus := -1
var _capture: AudioEffectCapture
var _player: AudioStreamPlayer
var _frames := PackedVector2Array()
var _seconds := 0.0


func _ready() -> void:
	ask_box.text_submitted.connect(func(t: String) -> void:
		if t.strip_edges() != "":
			asked.emit(t.strip_edges())
			ask_box.text = "")
	mic.pressed.connect(_toggle_mic)
	$speed/slow.pressed.connect(func() -> void: speed_changed.emit(0.5))
	$speed/normal.pressed.connect(func() -> void: speed_changed.emit(1.0))
	$speed/fast.pressed.connect(func() -> void: speed_changed.emit(5.0))
	$free.pressed.connect(func() -> void: free_walk.emit())
	card.visible = false


func show_line(text: String) -> void:
	line_label.text = text


func show_card(text: String) -> void:
	card_text.text = text
	card.visible = text != ""


func set_clock(minutes: float, speed: float) -> void:
	var day := int(minutes / 1440.0) + 1
	var m := int(minutes) % 1440
	clock_label.text = "Day %d, %02d:%02d   ·   %s" % [day, m / 60, m % 60, "%.1f simulated minutes a second" % speed]


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
	mic.text = "■ Stop"
	hint.text = "Listening… ask your question, then press Stop."


func _stop() -> void:
	recording = false
	_player.stop()
	mic.text = "🎤 Ask aloud"
	hint.text = "Writing down what you said…"
	recorded.emit(_wav(_frames, int(AudioServer.get_mix_rate())))


func _process(dt: float) -> void:
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
