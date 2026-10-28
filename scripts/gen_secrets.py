#!/usr/bin/env python3
"""
Atlas-Quant Secret Generator & Token Rotator.
Generates strong cryptographic random tokens (token_urlsafe(32)) for:
  - ADMIN_API_KEY
  - ADMIN_EMERGENCY_KILL_TOKEN
  - ADMIN_RESET_TOKEN
  - ADMIN_HMAC_SECRET

Rotates any known public default literals on sight and leaves previously
generated secure secrets intact (idempotent).
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

# Target keys managed by this script
MANAGED_KEYS = [
    "ADMIN_API_KEY",
    "ADMIN_EMERGENCY_KILL_TOKEN",
    "ADMIN_RESET_TOKEN",
    "ADMIN_HMAC_SECRET",
]

# Known public default literals to rotate on sight
PUBLIC_LITERALS = {
    "EMERGENCY_KILL_AUTHORIZED",
    "ADMIN_RESET_CONFIRMED",
    "atlas_quant_admin_hmac_secret_2026",
    "atlas_live_trading_secret_key_2026",
}


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def main() -> None:
    # Resolve .env file path
    base_dir = Path(__file__).resolve().parent.parent
    env_file = base_dir / ".env"
    env_example = base_dir / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            print(f"Creating .env from {env_example.name}...")
            env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            print("Creating empty .env file...")
            env_file.touch()

    lines = env_file.read_text(encoding="utf-8").splitlines()

    new_lines = []
    found_keys = set()
    generated = []
    rotated = []
    kept = []

    pattern = re.compile(r"^([A-Z0-9_]+)\s*=\s*(.*)$")

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            key, val = match.group(1), match.group(2)
            if key in MANAGED_KEYS:
                found_keys.add(key)
                clean_val = val.split("#", 1)[0].strip()
                if (clean_val.startswith('"') and clean_val.endswith('"')) or (
                    clean_val.startswith("'") and clean_val.endswith("'")
                ):
                    clean_val = clean_val[1:-1].strip()

                if clean_val in PUBLIC_LITERALS:
                    new_token = generate_token()
                    new_lines.append(f'{key}="{new_token}"')
                    rotated.append(key)
                    continue
                elif not clean_val:
                    new_token = generate_token()
                    new_lines.append(f'{key}="{new_token}"')
                    generated.append(key)
                    continue
                else:
                    new_lines.append(line)
                    kept.append(key)
                    continue

        new_lines.append(line)

    missing_keys = [k for k in MANAGED_KEYS if k not in found_keys]
    if missing_keys:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append("# Admin Security Tokens (Auto-generated)")
        for key in missing_keys:
            new_token = generate_token()
            new_lines.append(f'{key}="{new_token}"')
            generated.append(key)

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    print("Atlas-Quant Secret Generator Status:")
    if generated:
        print(f"  Generated ({len(generated)}): {', '.join(generated)}")
    if rotated:
        print(f"  Rotated public defaults ({len(rotated)}): {', '.join(rotated)}")
    if kept:
        print(f"  Kept existing secure secrets ({len(kept)}): {', '.join(kept)}")
    if not generated and not rotated:
        print("  All secrets are already configured and secure (idempotent).")


if __name__ == "__main__":
    main()

