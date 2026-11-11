# Known limitations

- Scale is arbitrary (structure-from-motion is up-to-scale). Metric accuracy has not been validated against ground truth.
- Only surfaces seen in the photographs are reconstructed. Unphotographed regions (e.g. rooftops) are missing.
- Glass, mirrors, glossy and untextured surfaces reconstruct poorly (holes, noise, failed matching).
- Reprojection error measures internal consistency, not accuracy.
- Mesh simplification ratio (default 0.05) was chosen for file size and has not been measured against the full mesh.
- Feature matching is exhaustive (quadratic in image count); several stages are CPU-bound. Dense reconstruction needs a CUDA GPU (Colab T4).
- COLMAP's coordinate frame is arbitrary; models may import rotated.
- Video support is validated only up to the sparse stage. Frame selection is naive (fixed rate, then blur filtering).
- Validated on one photo dataset (front of one house).

## Added during the speed/AR sprint
- Gaussian splats show white haze and stray shards at the edges of the capture (thinly covered areas). A strict opacity cleanup removes about half of the Gaussians but not all of the haze. Not solved.
- Splat quality numbers (PSNR/SSIM/LPIPS) depend on image size and are measured before cleanup; compare runs only at the same resolution.
- The splat's coordinate frame (up, heading, scale) is not exported; viewers must set it by eye.
- AR files (GLB/USDZ) are unscaled unless `ar.scale_factor` is set; scale comes from one manual reference distance and is only as accurate as that reference. Large subjects (buildings) are poor AR assets.
- USDZ export uses Blender's exporter and has only been tested on the build in this repo; test on a real iPad before relying on it.
- Colab sessions can stop responding mid-job; the executor waits and retries but a run can still fail.