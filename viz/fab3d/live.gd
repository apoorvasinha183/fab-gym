extends Node
## The link to the helper (docs/FAB-3D.md): it starts a whole-fab run, then asks for the state of the cells the scene
## holds, the carriers' moves over the next minutes included, and passes questions and recordings on. On the Mac the
## helper is at 127.0.0.1:8766; in the browser the scene is served by the helper, so it asks its own address. From the
## SMT2020 testbed; not a real fab.

signal run_ready(info: Dictionary)
signal state(d: Dictionary)
signal answered(d: Dictionary)
signal heard(d: Dictionary)
signal failed(where: String, message: String)
signal lou_replied(d: Dictionary)      # Lou's Meta brain answered (docs/FAB-3D.md, F11)

var base := "http://127.0.0.1:8766"
var run_id := ""
var offline := false
var demo: Dictionary = {}
var _busy := false
var _run: HTTPRequest
var _state: HTTPRequest
var _ask: HTTPRequest
var _voice: HTTPRequest
var _lou: HTTPRequest


func _ready() -> void:
	if OS.has_feature("web"):
		base = str(JavaScriptBridge.eval("location.origin"))
	var path := "res://data/demo.json"
	if FileAccess.file_exists(path):
		demo = JSON.parse_string(FileAccess.get_file_as_string(path))
	_run = _make("_on_run")
	_run.timeout = 3.0
	_state = _make("_on_state")
	_ask = _make("_on_ask")
	_voice = _make("_on_voice")
	_lou = _make("_on_lou")
	_lou.timeout = 180.0    # Muse Spark Open takes 5 to 8 s; a what-if reruns the day on the simulator


func _make(handler: String) -> HTTPRequest:
	var r := HTTPRequest.new()
	r.timeout = 60.0
	add_child(r)
	r.request_completed.connect(Callable(self, handler))
	return r


func _post(r: HTTPRequest, path: String, body: Dictionary) -> void:
	var err := r.request(base + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(body))
	if err != OK:
		if r == _run:
			_use_demo()
		elif r == _state:
			_busy = false
		else:
			failed.emit("request", "That request is still running. Please try again in a moment.")


func _use_demo() -> void:
	if not demo.get("frames", []).is_empty():
		offline = true
		run_id = "recorded-demo"
		run_ready.emit({"offline": true})
	else:
		failed.emit("run", "Live data is offline. You can still tour and explore.")


func start(seed := 1, days := 1.0, overrides = null) -> void:
	if run_id == "" and not demo.is_empty():
		_use_demo()
	var body := {"seed": seed, "days": days}
	if overrides != null:
		body["overrides"] = overrides
	_post(_run, "/api/fab3d/run", body)


func ask_state(t: float, cells: Array, span := 2.0) -> void:
	if offline:
		var i := clampi(int((t - float(demo["start"])) / float(demo["every"])), 0, demo["frames"].size() - 1)
		state.emit(demo["frames"][i])
		return
	if run_id == "" or _busy:
		return
	_busy = true
	_post(_state, "/api/fab3d/state", {"run": run_id, "t": t, "cells": cells, "span": span})


func ask(question: String) -> void:
	if offline:
		answered.emit({"error": "This question needs a live connection. Explore the tool cards or try asking what an area does."})
		return
	_post(_ask, "/api/glossary/ask", {"question": question})


func cancel_question() -> void:
	if _lou:
		_lou.cancel_request()


func lou(question: String, t: float, near_area: String) -> void:
	# Lou's Meta brain: the question, the scene's minute and the area the visitor stands in
	_post(_lou, "/api/lou/ask", {"question": question, "run": run_id, "t": t, "near_area": near_area})


func voice(wav: PackedByteArray) -> void:
	if offline:
		heard.emit({"error": "Speech needs a live connection. You can type your question instead."})
		return
	_post(_voice, "/api/voice", {"audio": Marshalls.raw_to_base64(wav), "mime": "audio/wav"})


func _read(result: int, code: int, body: PackedByteArray, where: String) -> Variant:
	if result != HTTPRequest.RESULT_SUCCESS or code < 200 or code >= 300:
		failed.emit(where, "The helper did not answer (is it running on 8766?).")
		return null
	var d = JSON.parse_string(body.get_string_from_utf8())
	if typeof(d) != TYPE_DICTIONARY:
		failed.emit(where, "The helper's answer was not readable.")
		return null
	return d


func _on_run(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "run")
	if d == null or not d.has("run"):
		_use_demo()
		return
	if d.has("run"):
		offline = false
		run_id = str(d["run"])
		run_ready.emit(d)
	else:
		failed.emit("run", str(d.get("error", "The run did not start.")))


func _on_state(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	_busy = false
	var d = _read(result, code, body, "state")
	if d != null and not d.has("error"):
		state.emit(d)
	else:
		_use_demo()


func _on_ask(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "ask")
	if d != null:
		answered.emit(d)


func _on_voice(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "voice")
	if d != null:
		heard.emit(d)


func _on_lou(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "lou")
	lou_replied.emit(d if d != null else {"fallback": true, "message": "The helper did not answer."})
