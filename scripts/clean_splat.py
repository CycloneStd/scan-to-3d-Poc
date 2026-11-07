import argparse

import numpy as np

READ = {"float": "<f4", "float32": "<f4", "double": "<f8", "uchar": "u1", "uint8": "u1", "int": "<i4",
        "int32": "<i4", "uint": "<u4", "short": "<i2", "ushort": "<u2", "char": "i1"}
WRITE = {"<f4": "float", "<f8": "double", "u1": "uchar", "<i4": "int", "<u4": "uint", "<i2": "short",
         "<u2": "ushort", "i1": "char"}


def read_ply(path):
    props, n, in_vertex = [], None, False
    with open(path, "rb") as fh:
        while True:
            line = fh.readline().decode("ascii").strip()
            if line.startswith("format") and "binary_little_endian" not in line:
                raise SystemExit("Only binary little-endian PLY files are supported")
            if line.startswith("element"):
                parts = line.split()
                in_vertex = parts[1] == "vertex"
                if in_vertex:
                    n = int(parts[2])
            elif line.startswith("property") and in_vertex:
                _, typ, name = line.split()
                props.append((name, READ[typ]))
            elif line == "end_header":
                break
        return np.fromfile(fh, dtype=np.dtype(props), count=n), props


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--min-opacity", type=float, default=0.3)
    ap.add_argument("--max-scale-frac", type=float, default=0.05,
                    help="largest allowed Gaussian size as a fraction of the scene radius (0 = off)")
    ap.add_argument("--crop-factor", type=float, default=1.5,
                    help="keep Gaussians within this multiple of the scene radius (0 = off)")
    a = ap.parse_args()

    d, props = read_ply(a.src)
    n0 = len(d)
    xyz = np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64)
    opacity = 1 / (1 + np.exp(-d["opacity"].astype(np.float64)))                # stored as logit
    size = np.exp(np.max(np.stack([d["scale_0"], d["scale_1"], d["scale_2"]], 1), axis=1).astype(np.float64))
    solid = opacity > 0.5
    center = np.median(xyz[solid], axis=0)
    dist = np.linalg.norm(xyz - center, axis=1)
    radius = float(np.percentile(dist[solid], 90))

    q = lambda v: " / ".join(f"{np.percentile(v, p):.4g}" for p in (5, 50, 95))
    print(f"{n0:,} Gaussians. scene radius (90th pct of solid ones): {radius:.4g}")
    print(f"opacity p5/p50/p95: {q(opacity)}   size p5/p50/p95: {q(size)}")

    keep = np.ones(n0, bool)

    def apply(label, mask):
        nonlocal keep
        before = int(keep.sum())
        keep &= mask
        print(f"{label:<34} removed {before - int(keep.sum()):>9,}   remaining {int(keep.sum()):>9,}")

    apply(f"opacity >= {a.min_opacity}", opacity >= a.min_opacity)
    if a.max_scale_frac > 0:
        apply(f"size <= {a.max_scale_frac} x radius", size <= a.max_scale_frac * radius)
    if a.crop_factor > 0:
        apply(f"distance <= {a.crop_factor} x radius", dist <= a.crop_factor * radius)

    out = d[keep]
    header = "ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % len(out)
    header += "".join(f"property {WRITE[t]} {name}\n" for name, t in props) + "end_header\n"
    with open(a.dst, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(out.tobytes())
    print(f"Wrote {a.dst}: {len(out):,} Gaussians ({100 * len(out) / n0:.1f}% kept)")


if __name__ == "__main__":
    main()