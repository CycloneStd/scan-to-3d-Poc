
from pathlib import Path
import subprocess
import sys


class ColmapRunner:
    def __init__(self, executable: Path) -> None:
        self.executable = Path(executable)

    def run(self, arguments: list[str], *, verbose: bool = True) -> None:
        if not self.executable.exists():
            raise FileNotFoundError(
                f"COLMAP executable was not found at: {self.executable}"
            )

        command = [str(self.executable), *arguments]

        # Windows needs cmd.exe when invoking a .bat file.
        if sys.platform == "win32" and self.executable.suffix.lower() == ".bat":
            command = [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                subprocess.list2cmdline(command),
            ]

        output_lines: list[str] = []

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        if process.stdout is not None:
            for line in process.stdout:
                output_lines.append(line)
                if verbose:
                    sys.stdout.write(line)
                    sys.stdout.flush()

        process.wait()

        if process.returncode != 0:
            tail_lines = "".join(output_lines[-20:])
            raise RuntimeError(
                f"COLMAP failed with exit code {process.returncode} "
                f"for command: {' '.join(command)}\n"
                f"Error summary (last lines):\n{tail_lines}"
            )