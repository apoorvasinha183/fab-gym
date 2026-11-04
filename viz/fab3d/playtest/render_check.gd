extends SceneTree
## A short visible sweep of every camera context, with small stills for review.

var game: Node
var out := ""


func _initialize() -> void:
	_run.call_deferred()


func shot(name: String) -> void:
	await process_frame
	await process_frame
	await RenderingServer.frame_post_draw
	var img := root.get_texture().get_image()
	img.resize(1280, 720, Image.INTERPOLATE_LANCZOS)
	img.save_png(out.path_join(name + ".png"))
	print("camera still: ", name)


func _run() -> void:
	var args := OS.get_cmdline_user_args()
	out = args[args.find("--render-check") + 1]
	DirAccess.make_dir_recursive_absolute(out)
	game = load("res://main.tscn").instantiate()
	root.add_child(game)
	await create_timer(1, true).timeout
	await shot("01-welcome")
	game.play_menu.close()
	game.live._use_demo()
	game.choose_view("tour")
	game.drone.playing = false
	game.drone._place(9.0)
	await shot("02-opening-flight")
	game._free_walk()
	game.travel_to("Phase one")
	await create_timer(2).timeout
	await shot("03-walking")
	game.choose_view("fly")
	await create_timer(1).timeout
	await shot("04-flying")
	game.travel_to("Phase two")
	await create_timer(2).timeout
	await shot("05-phase-two")
	game.travel_to("Cinema")
	await create_timer(1).timeout
	await shot("06-cinema-lobby")
	game.cinema.sit("R5C4")
	await create_timer(1).timeout
	await shot("07-seated")
	game.cinema.play()
	game.cinema.fullscreen(true)
	await create_timer(3).timeout
	await shot("08-movie")
	game.cinema.fullscreen(false)
	game.cinema.stand()
	game.play_menu.open()
	await shot("09-pause")
	quit()
