#!/usr/bin/env python3
"""Setup and manage aepipe configuration (base URL + ADMIN_TOKEN)."""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

CONFIG_DIR = os.path.expanduser("~/.config/query-aepipe")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    """Load existing config or return None."""
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(config):
    """Save config to disk."""
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)
    print(f"Config saved to {CONFIG_FILE}")


def test_connection(base_url, token):
    """Test connectivity by calling GET /v1/projects."""
    url = f"{base_url.rstrip('/')}/v1/projects"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "aepipe-client/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            projects = data.get("projects", [])
            print(f"Connection OK. Found {len(projects)} project(s): {projects}")
            return True
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Setup aepipe config")
    parser.add_argument("--base-url", help="aepipe worker base URL")
    parser.add_argument("--token", help="ADMIN_TOKEN for Bearer auth")
    parser.add_argument("--show", action="store_true", help="Show current config")
    parser.add_argument("--test", action="store_true", help="Test current config connectivity")
    parser.add_argument("--no-test", action="store_true", help="Skip connectivity test")
    args = parser.parse_args()

    if args.show:
        config = load_config()
        if config:
            masked = {**config, "admin_token": config["admin_token"][:8] + "..." if len(config.get("admin_token", "")) > 8 else "***"}
            print(json.dumps(masked, indent=2))
        else:
            print("No config found. Run setup first.")
        return

    if args.test:
        config = load_config()
        if not config:
            print("No config found. Run setup first.", file=sys.stderr)
            sys.exit(1)
        ok = test_connection(config["base_url"], config["admin_token"])
        sys.exit(0 if ok else 1)

    # Interactive or CLI setup
    base_url = args.base_url
    token = args.token

    if not base_url:
        existing = load_config()
        default = existing["base_url"] if existing else ""
        prompt = f"Base URL [{default}]: " if default else "Base URL (e.g. https://aepipe.example.com): "
        base_url = input(prompt).strip() or default
        if not base_url:
            print("Base URL is required.", file=sys.stderr)
            sys.exit(1)

    if not token:
        existing = load_config()
        default_hint = "(keep existing)" if existing and existing.get("admin_token") else ""
        prompt = f"ADMIN_TOKEN {default_hint}: " if default_hint else "ADMIN_TOKEN: "
        token = input(prompt).strip()
        if not token and existing and existing.get("admin_token"):
            token = existing["admin_token"]
        if not token:
            print("Token is required.", file=sys.stderr)
            sys.exit(1)

    # Remove trailing slash
    base_url = base_url.rstrip("/")

    if not args.no_test:
        print("Testing connection...")
        if not test_connection(base_url, token):
            answer = input("Connection failed. Save config anyway? [y/N]: ").strip().lower()
            if answer != "y":
                sys.exit(1)

    save_config({"base_url": base_url, "admin_token": token})


if __name__ == "__main__":
    main()
