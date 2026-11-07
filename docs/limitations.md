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