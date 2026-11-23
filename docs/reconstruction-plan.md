# Reconstruction plan and acceptance criteria

## Baseline

The supplied run registered 48 of 125 accepted photos and spent 817.4 seconds on PatchMatch. Earlier exhaustive runs in the downloaded logs registered 125 and spent roughly 4,800 to 5,050 seconds on PatchMatch. Feature extraction in those exhaustive runs took about seven to nine seconds. Compare runs on the same capture and report input, registered and dense-view counts alongside time.

The downloaded OBJ contains 300,841 triangles and 168 vertex-connected components. The largest component contains 142,480 of 150,749 vertices. The OBJ references a missing model.mtl. The GLB embeds an 8192 by 2595 PNG. Its facade has recognizable windows and brickwork. Large sheets extend into weakly observed regions. The exported mesh alone cannot establish their cause or dimensional accuracy.

## Implementation

1. Attempt camera registration with every readable JPEG or PNG. Group photos by dimensions and available EXIF camera, focal length and lens information. Score reduced-size previews. Record blur, exposure and clipping in the validation report.
2. Match unordered stills exhaustively within the current web upload limit. Use sequential matching for video. When registration falls below the configured threshold, recover the camera model with SuperPoint and LightGlue. Use all pairs for small recovery jobs and NetVLAD retrieval for larger ones. The recovery environment is installed on demand and adds cold-start time.
3. Before dense processing require a connected component meeting the registration threshold. Sample registered views using camera center and direction, with reduced priority for flagged views. The mesh track defaults to 48 dense views, six stereo source views and 1024-pixel depth maps in the house profile. Texture projection uses undistorted views up to 2400 pixels. Set dense.view_limit to zero to retain every registered view. Small sets use all available registered views. A two-view set can still lack sufficient support for dense fusion.
4. Keep the COLMAP dense path as the baseline. The optional OpenMVS backend imports the selected calibrated cameras, densifies with bounded resolution and constructs a visibility-based surface before existing texture and export steps. The two backends need comparison on the same GPU. Keep a separate splat track for view synthesis.
5. For the house profile, trim export triangles whose longest edge exceeds 12 times the median edge length of the textured surface. This can remove real long, thin features. Set mesh.max_edge_factor to null to disable it. The intermediate PLY remains available for comparison. Archive the material and texture with OBJ downloads. Fail export when Blender fails. Remove cross-job reuse that trusted stale files. Transfer archives using the configured upload concurrency. Reuse a textured mesh for AR when it already fits the face budget.

## Run and compare

Set inputs.photos_dir to the source folder. Use separate run IDs. For example:

```sh
scan3d run --config configs/house.yaml --run-id house-colmap --set inputs.photos_dir=Dataset/images
scan3d run --config configs/house.yaml --run-id house-openmvs --set inputs.photos_dir=Dataset/images --set dense.backend=openmvs
```

Use the same source photos, GPU and output requirements. Record cold-start, transfer and total wall time separately, plus time to the first usable model. Keep the 4 to 7 minute objective as a benchmark target. The manifest records camera registration by group, selected dense views, and stage timings. For OpenMVS the dense time includes fusion and the surface time corresponds to ReconstructMesh.

Evaluate mild and severe motion blur, low texture, mixed lenses, few-view sets and shuffled filenames. Compare held-out photographs against rendered views and use measured distances independent of the scale reference for dimensional error. Record holes, unsupported area, disconnected surfaces and recapture rate. Accept a new default only after it improves the target metrics without losing features such as window recesses or roof edges.

## Upstream implementations

- hloc provides a modular retrieval, local matching, geometric verification and mapping workflow. [Hierarchical Localization](https://github.com/cvg/Hierarchical-Localization)
- LightGlue adapts inference work per image pair. Its matching throughput alone cannot predict reconstruction wall time. [LightGlue](https://github.com/cvg/LightGlue)
- OpenMVS separates calibrated input, densification, surface reconstruction and texturing. [OpenMVS workflow](https://github.com/cdcseacave/openMVS/wiki/Usage)
- 2D Gaussian Splatting is another surface reconstruction approach with training and extraction stages. Changing to it would require validating a new mesh and texture delivery path. [2D Gaussian Splatting](https://github.com/hbb1/2d-gaussian-splatting)


## Local verification

The 128-photo house archive completed ingest in 0.85 seconds and validation in 11.4 seconds. All 128 were eligible for camera registration, including three flagged for blur. Two Colab sessions became unreachable before a result could be retrieved. The next CLI request required interactive Google authorization. Full GPU runtime, registration after mapping, and output accuracy remain unmeasured for these changes.
