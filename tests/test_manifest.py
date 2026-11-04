import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_manifest_matches_spec():
    manifest = json.loads((ROOT / "custom_components/returnright_rvm/manifest.json").read_text())
    assert manifest["domain"] == "returnright_rvm"
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["integration_type"] == "service"
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
    assert manifest["requirements"] == ["curl_cffi==0.17.0"]
    assert manifest["version"] == "0.1.0"
    assert manifest["documentation"].startswith("https://github.com/")
    assert manifest["issue_tracker"].startswith("https://github.com/")
    assert manifest["codeowners"]


def test_hacs_json_matches_spec():
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs == {"name": "Return Right RVM", "homeassistant": "2026.10.0", "country": "SG"}
