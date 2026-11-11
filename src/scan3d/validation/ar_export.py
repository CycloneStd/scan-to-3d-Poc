import json
import os
import sys

import bpy
from mathutils import Vector


def supported(operator, wanted):
    """Keep only the options this Blender version's exporter supports."""
    properties = set(operator.get_rna_type().properties.keys())
    return {key: value for key, value in wanted.items() if key in properties}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    args = dict(zip(argv[::2], argv[1::2]))
    source, output_dir = args["--input"], args["--outdir"]
    name = args.get("--name", "model_ar")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=source)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise SystemExit("No mesh was imported")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.shade_smooth()

    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    dimensions = [max(corner[i] for corner in corners) - min(corner[i] for corner in corners)
                  for i in range(3)]
    report = {
        "vertices": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "size_blender_x_y_z_up": [round(dimension, 4) for dimension in dimensions],
        "textures": {image.name: list(image.size) for image in bpy.data.images if image.has_data},
        "blender": bpy.app.version_string,
    }

    glb = os.path.join(output_dir, name + ".glb")
    try:
        kwargs = supported(bpy.ops.export_scene.gltf, {
            "filepath": glb, "export_format": "GLB", "export_image_format": "JPEG",
            "export_yup": True, "use_selection": True,
        })
        bpy.ops.export_scene.gltf(**kwargs)
        report["glb_bytes"] = os.path.getsize(glb)
    except Exception as exc:
        report["glb_error"] = repr(exc)

    usdz = os.path.join(output_dir, name + ".usdz")
    try:
        kwargs = supported(bpy.ops.wm.usd_export, {
            "filepath": usdz, "selected_objects_only": True, "export_materials": True,
            "generate_preview_surface": True, "export_textures_mode": "NEW", "export_textures": True,
            "convert_orientation": True, "export_global_forward_selection": "NEGATIVE_Z",
            "export_global_up_selection": "Y", "relative_paths": False,
        })
        bpy.ops.wm.usd_export(**kwargs)
        report["usdz_bytes"] = os.path.getsize(usdz)
        report["usd_options_used"] = sorted(kwargs)
    except Exception as exc:
        report["usdz_error"] = repr(exc)

    with open(os.path.join(output_dir, "ar_report.json"), "w") as report_file:
        json.dump(report, report_file, indent=2)


main()