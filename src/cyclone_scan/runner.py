
import subprocess
from pathlib import Path


class ColmapRunner:
    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def run(self, arguments: list[str]) -> None:
        command = [
            str(self.executable),
            *arguments,
        ]

        subprocess.run(
            command,
            check=True,
            shell=False,
        )