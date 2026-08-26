"""Node id -> human-readable name lookup for the RPi4 backend.

Every node in this deployment is a parking lot (LuckFox camera + ESP32-S3);
node 0 (the Gateway) is just the one that also happens to carry the
ENC28J60/RJ45 uplink to this RPi4, not a separate entrance/gate device --
there's no such node in this project yet. The chain/ESP-NOW protocol only
ever carries numeric node_id (see main/protocol.h); naming stays a
backend-side concern so relabeling a lot never needs a firmware reflash.
Edit node_names.json to name your actual nodes; anything not listed just
falls back to "node<N>".
"""

import json
import os

_NAMES_PATH = os.path.join(os.path.dirname(__file__), "node_names.json")


def load_names() -> dict[int, str]:
    if not os.path.exists(_NAMES_PATH):
        return {}
    with open(_NAMES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): v for k, v in raw.items()}


def name_for(node_id: int, names: dict[int, str]) -> str:
    return names.get(node_id, f"node{node_id}")
