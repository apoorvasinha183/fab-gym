extends Node3D
## The fab's structure from the IFC model (docs/BIM-3D.md): walls, columns, slabs, the raised floor and the filter
## ceiling, read from res://data/fab-building.glb (viz/bim/gltf.py; copied in by sync.sh). Each element keeps its
## IFC id and where its numbers come from as metadata, wears a saved material by name, and gets a box collider.
## A gigafab-style layout of our own design on the SMT2020 model; not a real fab.

const GLB := "res://data/fab-building.glb"
const MATERIALS := {
	"bim_wall": preload("res://bim/materials/bim_wall.tres"),
	"bim_column": preload("res://bim/materials/bim_column.tres"),
	"bim_slab_floor": preload("res://bim/materials/bim_slab_floor.tres"),
	"bim_slab_roof": preload("res://bim/materials/bim_slab_roof.tres"),
	"bim_covering_flooring": preload("res://bim/materials/bim_covering_flooring.tres"),
	"bim_covering_ceiling": preload("res://bim/materials/bim_covering_ceiling.tres"),
}
const BY_TYPE := {
	"IfcWall/SOLIDWALL": "bim_wall", "IfcWall/PARTITIONING": "bim_wall", "IfcColumn/COLUMN": "bim_column", "IfcSlab/FLOOR": "bim_slab_floor",
	"IfcSlab/ROOF": "bim_slab_roof", "IfcCovering/FLOORING": "bim_covering_flooring",
	"IfcCovering/CEILING": "bim_covering_ceiling",
}

var glb_path := GLB           # the fab's own building when the game shows a US fab (main.gd sets it)
var elements: Array = []      # {name, cls, type, node, aabb} in GlobalId order
var colliders: StaticBody3D
var loaded := false


func _ready() -> void:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	if not FileAccess.file_exists(glb_path) or doc.append_from_file(glb_path, state) != OK:
		push_error("no building: run viz/bim/gltf.py, then viz/godot-real/sync.sh")
		return
	var root := doc.generate_scene(state)
	add_child(root)
	colliders = StaticBody3D.new()
	colliders.name = "colliders"
	add_child(colliders)
	# the file's root node lists every element in order; Godot wraps it in one more node
	var gnodes: Array = state.json["nodes"]
	var holder: Node = root.get_child(0) if root.get_child_count() == 1 and root.get_child(0).get_child_count() > 0 else root
	for i in gnodes.size():
		var gn: Dictionary = gnodes[i]
		if not gn.has("mesh"):
			continue
		var mi := holder.get_child(i) as MeshInstance3D
		if mi == null or String(mi.name) != gn["name"]:
			push_error("building: element %d is not where the file puts it (%s, %s)" % [i, gn["name"], holder.get_child(i).name if i < holder.get_child_count() else "none"])
			return
		var x: Dictionary = gn["extras"]
		for k in x:
			mi.set_meta(k, x[k])
		var key := "%s/%s" % [x["Class"], x["PredefinedType"]]
		mi.set_surface_override_material(0, MATERIALS[BY_TYPE[key]])
		var box: AABB = mi.global_transform * mi.mesh.get_aabb()
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		bs.size = box.size
		cs.shape = bs
		cs.position = box.get_center()
		cs.set_meta("GlobalId", x["GlobalId"])
		colliders.add_child(cs)
		elements.append({"name": x["Name"], "cls": x["Class"], "type": x["PredefinedType"], "node": mi, "aabb": box})
	loaded = true


func cut_away() -> Array:
	## The roof and the filter ceiling, hidden whole when the building is cut open; walls are cut by height.
	var out: Array = []
	for e in elements:
		if e["type"] == "ROOF" or e["type"] == "CEILING":
			out.append(e["node"])
	return out


func report(every := 17) -> Dictionary:
	var nodes := {}
	var samples: Array = []
	for i in elements.size():
		var e: Dictionary = elements[i]
		nodes[e["cls"]] = nodes.get(e["cls"], 0) + 1
		if i % every == 0:
			var b: AABB = e["aabb"]
			samples.append([e["name"], [b.position.x, b.position.y, b.position.z], [b.end.x, b.end.y, b.end.z]])
	return {"elements": elements.size(), "nodes": nodes, "colliders": colliders.get_child_count() if colliders else 0, "samples": samples}
