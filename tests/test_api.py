"""Tests for the async upstream client."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from custom_components.returnright_rvm.api import (
    RvmAuthError,
    RvmBlockedError,
    RvmClient,
    RvmConnectionError,
    RvmPostcodeNotFoundError,
    Tokens,
)
from custom_components.returnright_rvm.models import Compartment, Machine

FIXTURES = Path(__file__).parent / "fixtures"
TOKENS = Tokens(uuid="u-1", token="t-1")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _recorded_error(name: str) -> "StubResponse":
    """Parse a recorded 'status=/content-type=/blank/body' fixture."""
    head, _, body = _fixture(name).partition("\n\n")
    meta = dict(line.split("=", 1) for line in head.splitlines())
    return StubResponse(int(meta["status"]), body, {"Content-Type": meta["content-type"]})


class StubResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"Content-Type": "application/json"}

    def json(self) -> Any:
        return json.loads(self.text)


class StubSession:
    def __init__(self, *responses: Any):
        self._queue = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict[str, str] | None] = []
        self.closed = False

    async def get(self, url, headers=None):
        self.urls.append(url)
        self.headers.append(headers)
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True


def _ok(name: str) -> StubResponse:
    return StubResponse(text=_fixture(name))


async def test_get_tokens_chains_map_token_then_access_token():
    session = StubSession(
        StubResponse(text='{"status":"ok","data":{"uuid":"abc","expiresIn":60}}'),
        StubResponse(text='{"status":"ok","data":{"token":"tok","expiresAt":1}}'),
    )
    tokens = await RvmClient(session).get_tokens()
    assert tokens == Tokens(uuid="abc", token="tok")
    assert session.urls[0].endswith("/map-token")
    assert session.urls[1].endswith("/abc/locations/access-token")
    assert all(h["x-bcrs-client"] == "web" for h in session.headers)


async def test_get_tokens_recorded_fixtures():
    session = StubSession(_ok("map_token.json"), _ok("access_token.json"))
    tokens = await RvmClient(session).get_tokens()
    assert tokens.token.startswith("REDACTED")


async def test_get_tokens_unexpected_body_raises():
    session = StubSession(StubResponse(text='{"status":"ok","data":{}}'))
    with pytest.raises(RvmConnectionError, match="unexpected response"):
        await RvmClient(session).get_tokens()


async def test_nearby_sends_token_header_and_parses_all_machines():
    session = StubSession(_ok("nearby_1500.json"))
    machines = await RvmClient(session).nearby(TOKENS, 1.37, 103.87, 1500)
    assert len(machines) == 18
    assert all(isinstance(m, Machine) for m in machines)
    assert machines[0].id == 1203
    assert "/u-1/locations/nearby" in session.urls[0]
    for part in ("lat=1.37", "lng=103.87", "radius=1500"):
        assert part in session.urls[0]
    assert session.headers[0]["x-bcrs-map-token"] == "t-1"
    assert session.headers[0]["x-bcrs-client"] == "web"


async def test_nearby_skips_malformed_record_and_keeps_the_rest(caplog):
    records = json.loads(_fixture("nearby_statuses.json"))
    records["data"][1] = {"id": 2820}
    session = StubSession(StubResponse(text=json.dumps(records)))
    with caplog.at_level(logging.WARNING):
        machines = await RvmClient(session).nearby(TOKENS, 1.0, 103.0, 1500)
    assert [m.id for m in machines] == [1156, 3098, 1203]
    assert "malformed" in caplog.text


async def test_bin_status_returns_compartments():
    session = StubSession(_ok("bin_status_1157.json"))
    result = await RvmClient(session).bin_status(TOKENS, 1157)
    assert len(result) == 1
    assert isinstance(result[0], Compartment)
    assert (result[0].type, result[0].fill_pct) == ("CAN PET", 40)
    assert session.urls[0].endswith("/locations/rvms/1157/bin-status")
    assert session.headers[0]["x-bcrs-map-token"] == "t-1"


async def test_bin_status_empty_data_returns_empty_list():
    session = StubSession(StubResponse(text='{"status":"ok","data":[]}'))
    assert await RvmClient(session).bin_status(TOKENS, 1) == []


async def test_bin_status_unexpected_body_raises():
    session = StubSession(StubResponse(text='{"status":"ok"}'))
    with pytest.raises(RvmConnectionError, match="unexpected response"):
        await RvmClient(session).bin_status(TOKENS, 1)


async def test_forbidden_html_is_blocked():
    session = StubSession(_recorded_error("blocked_response.txt"))
    with pytest.raises(RvmBlockedError):
        await RvmClient(session).bin_status(TOKENS, 1)


async def test_forbidden_json_is_auth_error():
    session = StubSession(_recorded_error("invalid_token_response.txt"))
    with pytest.raises(RvmAuthError):
        await RvmClient(session).bin_status(TOKENS, 1)


async def test_header_lookup_is_case_insensitive():
    resp = _recorded_error("invalid_token_response.txt")
    resp.headers = {"content-type": "application/json; charset=utf-8"}
    with pytest.raises(RvmAuthError):
        await RvmClient(StubSession(resp)).bin_status(TOKENS, 1)


async def test_200_with_non_json_body_is_blocked():
    session = StubSession(StubResponse(text="<html>nope</html>"))
    with pytest.raises(RvmBlockedError):
        await RvmClient(session).bin_status(TOKENS, 1)


async def test_500_is_connection_error():
    session = StubSession(StubResponse(status_code=500, text="oops"))
    with pytest.raises(RvmConnectionError):
        await RvmClient(session).bin_status(TOKENS, 1)


async def test_transport_exception_is_connection_error():
    session = StubSession(OSError("boom"))
    with pytest.raises(RvmConnectionError):
        await RvmClient(session).get_tokens()


async def test_geocode_returns_lat_lng_address():
    body = '{"results":[{"LATITUDE":"1.35","LONGITUDE":"103.87","ADDRESS":"X"}]}'
    session = StubSession(StubResponse(text=body))
    assert await RvmClient(session).geocode("550509") == (1.35, 103.87, "X")
    assert "searchVal=550509" in session.urls[0]
    assert "x-bcrs-client" not in (session.headers[0] or {})


async def test_geocode_no_results_raises():
    session = StubSession(StubResponse(text='{"results":[]}'))
    with pytest.raises(RvmPostcodeNotFoundError):
        await RvmClient(session).geocode("000000")


async def test_close_closes_session():
    session = StubSession()
    await RvmClient(session).close()
    assert session.closed
