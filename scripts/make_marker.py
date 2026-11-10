#!/usr/bin/env python3
"""Make a printable A4 page with an ArUco scale marker (id 0, intended 100 mm)."""
import sys

import cv2
import numpy as np

SIDE_MM, DPI = 100, 300
mm = lambda v: int(round(v / 25.4 * DPI))

if not hasattr(cv2, "aruco"):
    sys.exit(f"This OpenCV ({cv2.__version__}) has no aruco module. Tell Claude.")

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
side = mm(SIDE_MM)
marker = cv2.aruco.generateImageMarker(dictionary, 0, side)        # includes its black border
page = np.full((mm(297), mm(210)), 255, np.uint8)                  # A4 portrait, white
y0, x0 = (page.shape[0] - side) // 2, (page.shape[1] - side) // 2
page[y0:y0 + side, x0:x0 + side] = marker
cv2.putText(page, "Cyclone scale marker ID 0 - intended 100 mm - MEASURE THE BLACK SQUARE",
            (mm(15), mm(285)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
try:
    from PIL import Image
    Image.fromarray(page).save("markers/marker_id0_A4.pdf", resolution=DPI)
    print("Wrote markers/marker_id0_A4.pdf")
except ImportError:
    cv2.imwrite("markers/marker_id0_A4.png", page)
    print("Wrote markers/marker_id0_A4.png (print it at 100% scale)")
