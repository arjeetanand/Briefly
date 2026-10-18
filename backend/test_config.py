from __future__ import annotations

import re
from pathlib import Path

from config import DEFAULTS


def test_root_env_template_matches_the_supported_configuration_catalog() -> None:
    template = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    template_keys = {
        match.group(1)
        for match in re.finditer(r"^([A-Z][A-Z0-9_]*)=", template, re.MULTILINE)
    }

    assert template_keys == set(DEFAULTS)
