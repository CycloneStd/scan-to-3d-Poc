
import subprocess
from pathlib import Path


class ColmapRunner:
    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def run(self, arguments: list[str]) -> None:
        command = [
            "cmd.exe",
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline(
                [str(self.executable), *arguments]
            ),
        ]

        subprocess.run(
            command,
            check=True,
            shell=False,
        )