extends SceneTree
## Render both real movies and check full-frame fitting and all caption text.

var failures := []
var out := ""


func _initialize() -> void:
	_run.call_deferred()


func check(ok: bool, label: String) -> void:
	print("PASS: " if ok else "FAIL: ", label)
	if not ok:
		failures.append(label)


func shot(name: String) -> void:
	await process_frame
	await process_frame
	RenderingServer.force_draw()
	root.get_texture().get_image().save_png(out.path_join(name + ".png"))


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	out = args[args.find("--cinema-check") + 1]
	DirAccess.make_dir_recursive_absolute(out)
	var game = load("res://main.tscn").instantiate()
	root.add_child(game)
	await process_frame
	game.play_menu.close()
	game.travel_to("Cinema")
	game.cinema.sit("R5C4")
	var cinema = game.cinema
	check(cinema.titles.size() == 2, "both films are bundled")
	check(cinema.picture.stretch_mode == TextureRect.STRETCH_KEEP_ASPECT_CENTERED, "full screen fits the complete frame")
	for film in 2:
		cinema.pick(film)
		await shot("%d-title" % film)
		check(not cinema.captions.is_empty(), "film %d includes its caption track" % film)
		cinema.set_process(false)
		for cue in cinema.captions:
			cinema.subtitle.text = cue.text
			await process_frame
			check(cinema.subtitle.get_line_count() <= cinema.subtitle.get_visible_line_count(), "caption fits: " + str(cue.text).left(32))
		cinema.set_process(true)
		cinema.play()
		cinema.fullscreen(true)
		await create_timer(float(cinema.captions[0].start) + 0.7).timeout
		cinema.user_paused = true
		cinema.video.paused = true
		check(cinema.video.stream_position > 0.5, "film %d actually decodes and plays" % film)
		check(not cinema.subtitle.text.is_empty(), "film %d displays timed captions" % film)
		for size in [Vector2i(1280, 720), Vector2i(800, 1000), Vector2i(1920, 720)]:
			root.size = size
			await shot("%d-full-%dx%d" % [film, size.x, size.y])
			check(cinema.picture.get_global_rect().size.x >= 800, "movie area follows window width")
		cinema.fullscreen(false)
		root.size = Vector2i(1280, 720)
		await shot("%d-hall" % film)
	FileAccess.open(out.path_join("result.json"), FileAccess.WRITE).store_string(JSON.stringify({"failures": failures}, "  "))
	quit(0 if failures.is_empty() else 1)
