"""Install the pipeline's Blender runtime from the official pinned Linux archive."""
import hashlib
import tarfile
import tempfile
import urllib.request
from pathlib import Path


VERSION = "4.5.14"
ARCHIVE = f"blender-{VERSION}-linux-x64.tar.xz"
BASE_URL = f"https://download.blender.org/release/Blender4.5/{ARCHIVE}"
EXPECTED_SHA256 = "9ba871ff2ecd36526b77432745980b7e6664ecd0c7ca11c48849073dcfe06da3"
DESTINATION = Path("/opt/blender")


def main() -> None:
    digest = hashlib.sha256()
    with tempfile.TemporaryFile() as payload:
        with urllib.request.urlopen(BASE_URL, timeout=60) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                digest.update(chunk)
                payload.write(chunk)
        actual = digest.hexdigest()
        if actual != EXPECTED_SHA256:
            raise SystemExit(f"Blender archive checksum mismatch: {actual}")
        payload.seek(0)
        _extract(payload)


def _extract(payload) -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    prefix = f"blender-{VERSION}-linux-x64/"
    with tarfile.open(fileobj=payload, mode="r:xz") as archive:
        for member in archive.getmembers():
            if not member.name.startswith(prefix):
                raise SystemExit("Unexpected path in Blender archive")
            relative = member.name[len(prefix):]
            if not relative:
                continue
            target = (DESTINATION / relative).resolve()
            if not target.is_relative_to(DESTINATION.resolve()):
                raise SystemExit("Unsafe path in Blender archive")
            member.name = relative
            archive.extract(member, DESTINATION, filter="data")

    executable = DESTINATION / "blender"
    executable.chmod(executable.stat().st_mode | 0o111)
    link = Path("/usr/local/bin/blender")
    link.symlink_to(executable)
    print(f"Installed Blender {VERSION} at {executable}")


if __name__ == "__main__":
    main()
