from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def main() -> None:
    try:
        import keyring
    except ImportError as exc:
        raise SystemExit("Install the Colab CLI first: uv tool install google-colab-cli") from exc

    token = keyring.get_password("google-colab-cli", "oauth_token")
    if not token:
        raise SystemExit(
            "No Google Colab CLI token was found in this computer's keyring. "
            "Run `colab sessions` here, finish Google sign-in, then run this command again."
        )
    try:
        credentials = json.loads(token)
    except json.JSONDecodeError as exc:
        raise SystemExit("The Colab CLI keyring entry is not valid JSON; reauthorize with `colab sessions`.") from exc
    if not credentials.get("refresh_token"):
        raise SystemExit("The stored Colab credentials have no refresh token; reauthorize with `colab sessions`.")

    target = Path(__file__).resolve().parents[1] / "webxr" / "backend" / "colab-config" / "token.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(token)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Colab token exported to {target}. Keep this file secret and do not commit it.")


if __name__ == "__main__":
    main()
