
from pathlib import Path
import subprocess
import sys


class ColmapRunner:
    def __init__(self, executable: Path) -> None:
        self.executable = Path(executable)

    def help_text(self, subcommand: str) -> str:
        if not self.executable.exists():
            raise FileNotFoundError(
                f"COLMAP executable was not found at: {self.executable}"
            )
        command = [str(self.executable), subcommand, "-h"]
        if sys.platform == "win32" and self.executable.suffix.lower() == ".bat":
            command = [
                "cmd.exe",
                "/d",
                "/s",
                "/c",
                subprocess.list2cmdline(command),
            ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        output = f"{result.stdout}\n{result.stderr}".strip()
        if not output:
            raise RuntimeError(
                f"Unable to read COLMAP help for '{subcommand}' "
                f"(exit code {result.returncode})."
            )
        return output

    def run(
        self,
        arguments: list[str],
        *,
        verbose: bool = True,
        log_path: Path | None = None,
    ) -> None:
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
        log_file = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path.open("w", encoding="utf-8")

        try:
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
                    if log_file is not None:
                        log_file.write(line)
                    if verbose:
                        sys.stdout.write(line)
                        sys.stdout.flush()

            process.wait()
        finally:
            if log_file is not None:
                log_file.close()

        if process.returncode != 0:
            tail_lines = "".join(output_lines[-20:])
            raise RuntimeError(
                f"COLMAP failed with exit code {process.returncode} "
                f"for command: {' '.join(command)}\n"
                f"Error summary (last lines):\n{tail_lines}"
            )