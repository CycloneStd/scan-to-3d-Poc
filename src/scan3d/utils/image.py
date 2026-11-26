"""Bound image analysis to a small grayscale working copy."""
from pathlib import Path

import numpy as np
from PIL import Image


def grayscale_preview(path: Path):
    with Image.open(path) as image:
        size = image.size
        image.draft("L", (1024, 1024))
        image.thumbnail((1024, 1024), Image.Resampling.BOX)
        return size, np.asarray(image.convert("L"))


def sharpness(gray):
    pixels = gray.astype(np.int16)
    if min(pixels.shape) < 3:
        return 0.0
    laplacian = (pixels[1:-1, :-2] + pixels[1:-1, 2:] + pixels[:-2, 1:-1]
                 + pixels[2:, 1:-1] - 4 * pixels[1:-1, 1:-1])
    return float(laplacian.var())
