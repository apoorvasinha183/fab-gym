extends RefCounted
## What is solid (docs/FAB-3D.md): walls, doors' frames, rails, benches, cars, trees, tools and stockers. The visitor
## slides along them, the camera stays on the near side of them, and the guide's route is checked against them (the
## air shower's bump is the one planned contact). Collision is built from the drawn meshes, or as boxes for the tools,
## which are drawn as instances. From the SMT2020 testbed; not a real fab.


static func meshes(root: Node, skip: Array = []) -> int:
	# a static trimesh body for every mesh under root, except under the nodes in skip (things that move)
	if root in skip:
		return 0
	var n := 0
	if root is MeshInstance3D and (root as MeshInstance3D).mesh:
		(root as MeshInstance3D).create_trimesh_collision()
		n += 1
	for c in root.get_children():
		n += meshes(c, skip)
	return n


static func boxes(parent: Node, list: Array, name: String) -> StaticBody3D:
	# one static body holding a box per [centre, size, yaw]
	var body := StaticBody3D.new()
	body.name = name
	for b in list:
		var cs := CollisionShape3D.new()
		var sh := BoxShape3D.new()
		sh.size = b[1]
		cs.shape = sh
		cs.transform = Transform3D(Basis(Vector3.UP, float(b[2])), b[0])
		body.add_child(cs)
	parent.add_child(body)
	return body
