from __future__ import annotations

import json
import os
from pathlib import Path


def _install_colab_token() -> None:
    token_json = os.environ.pop("COLAB_CLI_TOKEN_JSON", None)
    if not token_json:
        return

    try:
        token = json.loads(token_json)
    except json.JSONDecodeError as exc:
        raise SystemExit("COLAB_CLI_TOKEN_JSON must contain the exported Colab OAuth token JSON.") from exc
    if not isinstance(token, dict) or not token.get("refresh_token"):
        raise SystemExit("COLAB_CLI_TOKEN_JSON must contain a valid Colab OAuth refresh token.")

    target = Path.home() / ".config" / "colab-cli" / "token.json"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".json.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token_json)
    os.replace(temporary, target)
    os.chmod(target, 0o600)


def main() -> None:
    _install_colab_token()
    os.execvp("celery", ["celery", "-A", "app.worker:celery_app", "worker",
                         "--loglevel=INFO", "--concurrency=1"])


if __name__ == "__main__":
    main()
