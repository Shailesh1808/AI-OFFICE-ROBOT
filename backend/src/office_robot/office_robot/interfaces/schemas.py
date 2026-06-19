"""
interfaces/schemas.py — JSON contracts between layers.

Every topic that carries JSON uses one of these TypedDicts.
Nodes import from here instead of building dicts ad-hoc, so the
contract between layers is defined in one place.
"""

from typing import TypedDict, Literal


# ── Brain → Classifier ────────────────────────────────────────────────────────

class BrainQAPayload(TypedDict):
    """Published on /brain/qa by brain_node."""
    text: str          # the question to answer
    source: str        # "voice" | "screen" | "api"


class BrainNavigationPayload(TypedDict):
    """Published on /brain/navigation by brain_node (future)."""
    text: str          # raw navigation command text
    source: str


class BrainStopPayload(TypedDict):
    """Published on /brain/stop by brain_node (future)."""
    source: str


# ── Classifier → Output ───────────────────────────────────────────────────────

class SpeakerTextPayload(TypedDict):
    """Published on /outputs/speaker/text by any classifier that wants TTS output."""
    text: str          # text to speak aloud
    source: str        # "qa" | "navigation" | "system"


# ── Helpers ───────────────────────────────────────────────────────────────────

import json


def dump(payload: dict) -> str:
    return json.dumps(payload)


def load(data: str) -> dict:
    return json.loads(data)
