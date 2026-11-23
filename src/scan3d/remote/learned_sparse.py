"""Colab subprocess for recovering difficult captures with hloc."""
import json
import sys
from itertools import combinations
from pathlib import Path

import pycolmap
from hloc import extract_features, match_features, pairs_from_retrieval, reconstruction


def main(images, destination, camera_model):
    cache = destination.parent / "hloc"
    cache.mkdir(exist_ok=True)
    names = sorted(p.relative_to(images).as_posix() for p in images.rglob("*") if p.is_file())
    pairs = cache / "pairs.txt"
    if len(names) <= 32:
        pairs.write_text("".join(f"{a} {b}\n" for a, b in combinations(names, 2)))
    else:
        descriptors = extract_features.main(extract_features.confs["netvlad"], images, cache)
        pairs_from_retrieval.main(descriptors, pairs, num_matched=20)
    features = extract_features.main(extract_features.confs["superpoint_aachen"], images, cache)
    matches = match_features.main(match_features.confs["superpoint+lightglue"], pairs, features, matches=cache / "matches.h5")
    model = reconstruction.main(destination, images, pairs, features, matches,
                                camera_mode=pycolmap.CameraMode.PER_FOLDER,
                                image_options={"camera_model": camera_model})
    if model is None:
        raise RuntimeError("Learned matching could not register overlapping views.")
    print(json.dumps({"registered": model.num_reg_images()}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
