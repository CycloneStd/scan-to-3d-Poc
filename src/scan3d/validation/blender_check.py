import json
import os
import sys

import bpy
from mathutils import Vector


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    args = dict(zip(argv[::2], argv[1::2]))
    src, outdir = args["--input"], args["--outdir"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = src.lower().rsplit(".", 1)[-1]
    if ext == "obj":
        bpy.ops.wm.obj_import(filepath=src)
    elif ext == "ply":
        bpy.ops.wm.ply_import(filepath=src)
    else:
        raise SystemExit(f"Unsupported mesh format: {ext}")

    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    report = {
        "imported": bool(meshes),
        "objects": len(meshes),
        "vertices": sum(len(o.data.vertices) for o in meshes),
        "faces": sum(len(o.data.polygons) for o in meshes),
    }
    textures = sorted({
        n.image.name
        for o in meshes for slot in o.material_slots
        if slot.material and slot.material.use_nodes
        for n in slot.material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image
    })
    report["texture_images"] = textures

    if meshes:
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        center, size = (lo + hi) / 2, max(hi - lo)
        report["bbox_size"] = [round(v, 4) for v in (hi - lo)]

        bpy.ops.export_scene.gltf(filepath=os.path.join(outdir, "model.glb"), export_format="GLB")
        report["glb_bytes"] = os.path.getsize(os.path.join(outdir, "model.glb"))

        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x, scene.render.resolution_y = 1280, 800
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "TEXTURE" if textures else "VERTEX"
        cam_data = bpy.data.cameras.new("cam")
        cam_data.clip_end = size * 20
        cam = bpy.data.objects.new("cam", cam_data)
        scene.collection.objects.link(cam)
        scene.camera = cam
        views = {"px": (1, 0, 0), "nx": (-1, 0, 0), "py": (0, 1, 0), "ny": (0, -1, 0),
                 "pz": (0.001, 0.001, 1), "nz": (0.001, 0.001, -1)}
        for name, d in views.items():
            direction = Vector(d).normalized()
            cam.location = center + direction * size * 1.8
            cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = os.path.join(outdir, f"view_{name}.png")
            bpy.ops.render.render(write_still=True)
        report["renders"] = sorted(f"view_{n}.png" for n in views)

    with open(os.path.join(outdir, "blender_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)


main()