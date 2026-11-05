extends SceneTree
## Verify the four reception lightboxes and render front-facing proof of their full artwork.
var checks := {}

func _initialize() -> void:
	_run.call_deferred()

func expect(name: String, passed: bool) -> void:
	checks[name] = passed
	print("%s: %s" % ["PASS" if passed else "FAIL", name])

func _run() -> void:
	var game: Node = load("res://main.tscn").instantiate()
	root.add_child(game)
	await process_frame
	await process_frame
	game.play_menu.close()
	game.travel_to("Cinema")
	game.ui.visible = false
	var args := OS.get_cmdline_user_args()
	var out := args[args.find("--poster-check") + 1]
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1280, 720)
	game.player.camera.fov = 65
	expect("all four reception boards exist", game.cinema.posters == 4)
	for i in range(4):
		var frame: MeshInstance3D = game.cinema.get_node("Poster%d" % i)
		var art: MeshInstance3D = frame.get_node("Artwork")
		var texture: Texture2D = art.material_override.albedo_texture
		var fitted: Vector2 = art.mesh.size
		expect("poster %d retains full aspect and fits its lightbox" % i,
			is_equal_approx(fitted.x / fitted.y, texture.get_width() / float(texture.get_height()))
			and fitted.x <= frame.mesh.size.x and fitted.y <= frame.mesh.size.y)
		expect("poster %d faces visitors in the lobby" % i, (frame.global_basis * Vector3.BACK).dot(Vector3.FORWARD) > 0.99)
		game.player.global_position = Vector3(frame.global_position.x, frame.global_position.y, frame.global_position.z - 2.6)
		game.player.yaw = PI
		game.player.pitch = 0
		game.player.input_locked = true
		game.player.rotation.y = PI
		game.player.camera.rotation = Vector3.ZERO
		await create_timer(0.2).timeout
		if DisplayServer.get_name() != "headless":
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(out.path_join("poster-%d.png" % i))
	game.player.global_position = Vector3(59.4, 1.7, 98.7)
	await create_timer(0.2).timeout
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(out.path_join("reception.png"))
	FileAccess.open(out.path_join("checks.json"), FileAccess.WRITE).store_string(JSON.stringify(checks, "  "))
	quit(1 if false in checks.values() else 0)
