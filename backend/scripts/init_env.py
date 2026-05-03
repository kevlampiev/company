"""Generate a fresh .env at the repo root from .env.example with random secrets.

Usage (from `backend/`):
    uv run python -m scripts.init_env            # refuses to overwrite an existing .env
    uv run python -m scripts.init_env --force    # overwrite
    uv run python -m scripts.init_env --target /path/to/.env
"""

import argparse
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[2]


PLACEHOLDERS = {
    "changeme_strong_password": lambda: secrets.token_urlsafe(24),
    "change_me_jwt_secret_key_32_chars_min": lambda: secrets.token_urlsafe(48),
    "change_me_fernet_key_32url_safe_base64": lambda: Fernet.generate_key().decode(),
    "changeme_db_password": lambda: secrets.token_urlsafe(24),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing target")
    parser.add_argument(
        "--target",
        type=Path,
        default=REPO_ROOT / ".env",
        help=f"path to write (default: {REPO_ROOT / '.env'})",
    )
    args = parser.parse_args()

    example = REPO_ROOT / ".env.example"
    if not example.exists():
        print(f"error: {example} not found", file=sys.stderr)
        return 1

    if args.target.exists() and not args.force:
        print(f"error: {args.target} already exists; pass --force to overwrite", file=sys.stderr)
        return 1

    text = example.read_text(encoding="utf-8")
    for placeholder, generator in PLACEHOLDERS.items():
        if placeholder not in text:
            print(
                f"warning: placeholder {placeholder!r} not found in .env.example", file=sys.stderr
            )
            continue
        text = text.replace(placeholder, generator())

    args.target.write_text(text, encoding="utf-8")
    print(f"wrote {args.target} with random secrets")
    print("next: review the file, then `docker compose up -d --build`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
