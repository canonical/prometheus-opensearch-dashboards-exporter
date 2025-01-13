# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Fixtures for tests"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def api_response():
    current_dir = Path(__file__).parent
    json_file_path = current_dir / "dashboard_response.json"

    with open(json_file_path, "r") as f:
        data = json.load(f)

    return data
