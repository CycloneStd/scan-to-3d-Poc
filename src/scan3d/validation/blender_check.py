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
    tex_nodes = [
        n
        for o in meshes for slot in o.material_slots
        if slot.material and slot.material.use_nodes
        for n in slot.material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image
    ]
    textures = sorted({n.image.name for n in tex_nodes})
    report["texture_images"] = textures
    report["texture_sizes"] = {n.image.name: list(n.image.size) for n in tex_nodes}

    if meshes:
        for o in meshes:
            bpy.context.view_layer.objects.active = o
            try:
                bpy.ops.object.shade_smooth()
                if hasattr(o.data, "use_auto_smooth"):
                    o.data.use_auto_smooth = True
                    o.data.auto_smooth_angle = 0.523599
                else:
                    bpy.ops.object.modifier_add(type="WEIGHTED_NORMAL")
                    o.modifiers["WeightedNormal"].keep_sharp = True
            except Exception:
                pass

            for slot in o.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes:
                    continue
                mat.use_backface_culling = False
                principled = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if principled:
                    if "Roughness" in principled.inputs:
                        principled.inputs["Roughness"].default_value = 0.65
                    if "Specular" in principled.inputs:
                        principled.inputs["Specular"].default_value = 0.25
                    elif "Specular IOR Level" in principled.inputs:
                        principled.inputs["Specular IOR Level"].default_value = 0.25
                    if "Metallic" in principled.inputs:
                        principled.inputs["Metallic"].default_value = 0.0
                    tex = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
                    if tex and "Base Color" in principled.inputs:
                        mat.node_tree.links.new(tex.outputs["Color"], principled.inputs["Base Color"])

        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        center, size = (lo + hi) / 2, max(hi - lo)
        report["bbox_size"] = [round(v, 4) for v in (hi - lo)]

        glb_path = os.path.join(outdir, "model.glb")
        bpy.ops.export_scene.gltf(filepath=glb_path, export_format="GLB")
        report["glb_bytes"] = os.path.getsize(glb_path)
        report["renders"] = []

        # Only attempt workbench rendering if a display or GPU is available
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            try:
                scene.render.engine = "BLENDER_WORKBENCH"
                scene.render.resolution_x, scene.render.resolution_y = 1280, 800
                scene.display.shading.light = "STUDIO"
                scene.display.shading.color_type = "TEXTURE" if textures else "VERTEX"
                scene.display.shading.show_cavity = True
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
            except Exception:
                pass

    with open(os.path.join(outdir, "blender_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)


main()