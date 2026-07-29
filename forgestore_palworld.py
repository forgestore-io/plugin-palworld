#!/usr/bin/env python3
"""
ForgeStore — Palworld Server Plugin
=====================================
Automatically delivers purchases from your ForgeStore store to your Palworld server.

Requirements:
  - Python 3.8+
  - Palworld server with RESTAPIEnabled=True in PalWorldSettings.ini
  - pip install requests

Configuration:
  Edit the CONFIG section below, then run:
  python3 forgestore_palworld.py

PalWorldSettings.ini:
  RESTAPIEnabled=True
  RESTAPIPort=8212
  RESTAPIPassword=your_password
"""

import requests
import time
import logging
import sys
from typing import Optional

# ─── CONFIG ──────────────────────────────────────────────────────────────────
FORGESTORE_SECRET    = "YOUR_SECRET_KEY"       # Store Settings → Developers → API Keys
FORGESTORE_API_URL   = "https://forgestore.net/api/plugin"

PALWORLD_HOST        = "http://127.0.0.1"      # Your Palworld server host
PALWORLD_PORT        = 8212                    # RESTAPIPort from PalWorldSettings.ini
PALWORLD_PASSWORD    = "your_rest_password"    # RESTAPIPassword from PalWorldSettings.ini

POLL_INTERVAL        = 30                      # Seconds between polls
DEBUG_MODE           = False
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="[ForgeStore] %(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ForgeStore")

PALWORLD_BASE = f"{PALWORLD_HOST}:{PALWORLD_PORT}/v1"
FORGE_HEADERS = {
    "X-ForgeStore-Secret": FORGESTORE_SECRET,
    "Content-Type": "application/json",
    "User-Agent": "ForgeStore-Palworld/1.1.0",
}


# ─── Palworld API ─────────────────────────────────────────────────────────────

def palworld_request(method: str, endpoint: str, **kwargs):
    """Make a request to the Palworld REST API."""
    url = f"{PALWORLD_BASE}/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(
            method, url,
            auth=("admin", PALWORLD_PASSWORD),
            timeout=10,
            **kwargs
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {}
    except requests.exceptions.RequestException as e:
        log.warning(f"Palworld API error: {e}")
        return None


def get_online_players() -> list[str]:
    """Return list of online player names."""
    data = palworld_request("GET", "/players")
    if data and "players" in data:
        return [p.get("name", "").lower() for p in data["players"]]
    return []


def announce(message: str) -> bool:
    """Send a broadcast message to all players."""
    result = palworld_request("POST", "/announce", json={"message": message})
    return result is not None


def execute_command(command: str, player_name: str, package_name: str, order_id: int) -> bool:
    """
    Execute a ForgeStore delivery command.
    Palworld REST API doesn't have a generic command exec endpoint,
    so we handle supported command patterns.
    """
    cmd = command \
        .replace("{player}", player_name) \
        .replace("{player_name}", player_name) \
        .replace("{package}", package_name) \
        .replace("{order_id}", str(order_id))

    # Broadcast message
    if cmd.lower().startswith("broadcast ") or cmd.lower().startswith("say "):
        msg = cmd.split(" ", 1)[1] if " " in cmd else cmd
        return announce(msg)

    # Generic announce (default for unrecognized commands)
    log.info(f"  ↳ Executing: {cmd}")
    announce(f"[ForgeStore] {player_name} purchased {package_name}!")
    return True


# ─── ForgeStore API ───────────────────────────────────────────────────────────

def fetch_pending_commands() -> list[dict]:
    """Suit le vrai flux API: /queue -> /queue/offline (+ online/{player})."""
    def api_get(path):
        try:
            r = requests.get(f"{FORGESTORE_API_URL}{path}", headers=FORGE_HEADERS, timeout=15)
            if r.status_code == 401:
                log.error("❌ Invalid secret key. Check FORGESTORE_SECRET.")
                return None
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            log.warning(f"ForgeStore API error on {path}: {e}")
            return None

    q = api_get("/queue")
    if not isinstance(q, dict):
        return []

    out = []
    def normalize(c, fallback_name=""):
        p = c.get("player") or {}
        return {
            "id":          int(c.get("id", 0) or 0),
            "command":     c.get("command", "") or "",
            "player_name": p.get("name") or fallback_name or "",
            "player_uuid": p.get("uuid") or "",
            "delay":       int((c.get("conditions") or {}).get("delay", 0) or 0),
        }

    if (q.get("meta") or {}).get("execute_offline"):
        off = api_get("/queue/offline")
        if isinstance(off, dict):
            out.extend(normalize(c) for c in (off.get("commands") or []))

    for p in (q.get("players") or []):
        name = (p or {}).get("name")
        if not name:
            continue
        on = api_get(f"/queue/online/{name}")
        if isinstance(on, dict):
            out.extend(normalize(c, name) for c in (on.get("commands") or []))
    return out


def acknowledge_command(command_id: int) -> bool:
    """Confirme la livraison (DELETE /queue avec {"ids": [...]})."""
    try:
        resp = requests.delete(
            f"{FORGESTORE_API_URL}/queue",
            headers=FORGE_HEADERS,
            json={"ids": [int(command_id)]},
            timeout=10
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        log.warning(f"Ack error: {e}")
        return False


def test_connection() -> bool:
    """Test ForgeStore API connection."""
    try:
        r = requests.get(f"{FORGESTORE_API_URL}/information", headers=FORGE_HEADERS, timeout=10)
        return r.status_code == 200
    except Exception:
        return False

# ─── Main delivery loop ───────────────────────────────────────────────────────

def process_commands(commands: list[dict], online_players: list[str]):
    for cmd in commands:
        player_name = cmd.get("player_name", "")
        player_lower = player_name.lower()

        # Check if player is online (for player-targeted commands)
        if player_name and player_lower not in online_players:
            log.debug(f"  Player {player_name} offline — skipping #{cmd['id']}")
            continue

        package_name = cmd.get("package_name", "")
        order_id     = cmd.get("order_id", 0)
        command      = cmd.get("command", "")

        log.info(f"Delivering to {player_name}: {command}")
        success = execute_command(command, player_name, package_name, order_id)

        if success:
            if acknowledge_command(cmd["id"]):
                log.info(f"✅ Delivered and acknowledged #{cmd['id']}")
            else:
                log.warning(f"⚠️  Delivered but failed to acknowledge #{cmd['id']}")
        else:
            log.warning(f"❌ Failed to deliver #{cmd['id']}")


def main():
    log.info("ForgeStore Palworld Plugin v1.1.0 starting...")
    log.info(f"Palworld: {PALWORLD_BASE}")

    if not test_connection():
        log.error("❌ Cannot connect to ForgeStore API. Check FORGESTORE_SECRET.")
        sys.exit(1)
    log.info("✅ Connected to ForgeStore API")

    # Test Palworld connection
    info = palworld_request("GET", "/info")
    if info:
        log.info(f"✅ Connected to Palworld server: {info.get('servername', 'Unknown')}")
    else:
        log.error(f"❌ Cannot connect to Palworld REST API at {PALWORLD_BASE}")
        log.error("Make sure RESTAPIEnabled=True in PalWorldSettings.ini")
        sys.exit(1)

    log.info(f"Polling every {POLL_INTERVAL}s...")

    while True:
        try:
            commands = fetch_pending_commands()
            if commands:
                online = get_online_players()
                log.info(f"{len(commands)} pending command(s), {len(online)} online player(s)")
                process_commands(commands, online)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()