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

var base := "http://127.0.0.1:8766"
var run_id := ""
var _busy := false
var _run: HTTPRequest
var _state: HTTPRequest
var _ask: HTTPRequest
var _voice: HTTPRequest


func _ready() -> void:
	if OS.has_feature("web"):
		base = str(JavaScriptBridge.eval("location.origin"))
	_run = _make("_on_run")
	_state = _make("_on_state")
	_ask = _make("_on_ask")
	_voice = _make("_on_voice")


func _make(handler: String) -> HTTPRequest:
	var r := HTTPRequest.new()
	r.timeout = 60.0
	add_child(r)
	r.request_completed.connect(Callable(self, handler))
	return r


func _post(r: HTTPRequest, path: String, body: Dictionary) -> void:
	r.request(base + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(body))


func start(seed := 1, days := 1.0, overrides = null) -> void:
	var body := {"seed": seed, "days": days}
	if overrides != null:
		body["overrides"] = overrides
	_post(_run, "/api/fab3d/run", body)


func ask_state(t: float, cells: Array, span := 2.0) -> void:
	if run_id == "" or _busy:
		return
	_busy = true
	_post(_state, "/api/fab3d/state", {"run": run_id, "t": t, "cells": cells, "span": span})


func ask(question: String) -> void:
	_post(_ask, "/api/glossary/ask", {"question": question})


func voice(wav: PackedByteArray) -> void:
	_post(_voice, "/api/voice", {"audio": Marshalls.raw_to_base64(wav), "mime": "audio/wav"})


func _read(result: int, code: int, body: PackedByteArray, where: String) -> Variant:
	if result != HTTPRequest.RESULT_SUCCESS or code >= 500:
		failed.emit(where, "The helper did not answer (is it running on 8766?).")
		return null
	var d = JSON.parse_string(body.get_string_from_utf8())
	if typeof(d) != TYPE_DICTIONARY:
		failed.emit(where, "The helper's answer was not readable.")
		return null
	return d


func _on_run(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "run")
	if d == null:
		return
	if d.has("run"):
		run_id = str(d["run"])
		run_ready.emit(d)
	else:
		failed.emit("run", str(d.get("error", "The run did not start.")))


func _on_state(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	_busy = false
	var d = _read(result, code, body, "state")
	if d != null and not d.has("error"):
		state.emit(d)


func _on_ask(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "ask")
	if d != null:
		answered.emit(d)


func _on_voice(result: int, code: int, _h: PackedStringArray, body: PackedByteArray) -> void:
	var d = _read(result, code, body, "voice")
	if d != null:
		heard.emit(d)
