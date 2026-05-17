"""Tests for entity ID sanitization used during device/group discovery."""
from __future__ import annotations

import re


def _suggest_object_id(device_name: str) -> str:
    """Mirror entity_id logic from light.py async_setup_entry."""
    entity_id_base = device_name.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", entity_id_base).strip("_")


def test_suggest_object_id_from_device_name():
    """Device names map to clean Home Assistant object IDs."""
    assert _suggest_object_id("Kitchen Spot 1") == "kitchen_spot_1"
    assert _suggest_object_id("Hall-Way") == "hall_way"


def test_suggest_object_id_strips_special_characters():
    """Special characters are removed from suggested object IDs."""
    assert _suggest_object_id("Lamp (A)") == "lamp_a"
    assert _suggest_object_id("  Desk@2  ") == "desk2"
