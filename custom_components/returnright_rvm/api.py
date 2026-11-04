"""Async client for the Return Right upstream API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from curl_cffi.requests import AsyncSession

from .const import BASE_URL, ONEMAP_URL
from .models import (
    Compartment,
    Machine,
    parse_compartment,
    parse_machine,
)

_LOGGER = logging.getLogger(__name__)

_CLIENT_HEADERS = {"x-bcrs-client": "web"}


class RvmError(Exception):
    """Base error for the upstream client."""


class RvmConnectionError(RvmError):
    """Transport failure or unexpected upstream reply."""


class RvmBlockedError(RvmError):
    """The bot-protection gateway rejected the request."""


class RvmAuthError(RvmError):
    """The upstream rejected the token."""


class RvmPostcodeNotFoundError(RvmError):
    """Geocoding found nothing for the postcode."""


@dataclass(frozen=True)
class Tokens:
    """Token pair serving every call in a polling cycle."""

    uuid: str
    token: str


def make_session() -> AsyncSession:
    """Create a browser-impersonating session."""
    return AsyncSession(impersonate="chrome")


def _content_type(headers: Any) -> str:
    for key, value in headers.items():
        if key.lower() == "content-type":
            return str(value).lower()
    return ""


class RvmClient:
    """Client for the Return Right RVM endpoints and OneMap geocoding."""

    def __init__(self, session: Any) -> None:
        """Wrap a session with async get() and close()."""
        self._session = session

    async def _get_json(self, url: str, headers: dict[str, str] | None) -> Any:
        try:
            resp = await self._session.get(url, headers=headers)
        except Exception as err:
            raise RvmConnectionError(str(err)) from err
        is_json = "json" in _content_type(resp.headers)
        if resp.status_code == 403:
            if is_json:
                raise RvmAuthError("token rejected")
            raise RvmBlockedError("blocked by gateway")
        if resp.status_code != 200:
            raise RvmConnectionError(f"HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as err:
            raise RvmBlockedError("non-JSON response") from err

    async def _get_data(self, path: str, tokens: Tokens | None = None) -> Any:
        headers = dict(_CLIENT_HEADERS)
        if tokens:
            headers["x-bcrs-map-token"] = tokens.token
        body = await self._get_json(f"{BASE_URL}{path}", headers)
        try:
            return body["data"]
        except (KeyError, TypeError) as err:
            raise RvmConnectionError("unexpected response") from err

    async def get_tokens(self) -> Tokens:
        """Fetch a uuid, then an access token for it."""
        data = await self._get_data("/map-token")
        try:
            uuid = data["uuid"]
            token = (await self._get_data(f"/{uuid}/locations/access-token"))["token"]
        except (KeyError, TypeError) as err:
            raise RvmConnectionError("unexpected response") from err
        return Tokens(uuid=uuid, token=token)

    async def nearby(
        self, tokens: Tokens, lat: float, lng: float, radius_m: int
    ) -> list[Machine]:
        """List machines near a point, skipping unparseable records."""
        data = await self._get_data(
            f"/{tokens.uuid}/locations/nearby?lat={lat}&lng={lng}&radius={radius_m}",
            tokens,
        )
        machines = []
        for record in data:
            try:
                machines.append(parse_machine(record))
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipping malformed machine record: %s", record)
        return machines

    async def bin_status(self, tokens: Tokens, rvm_id: int) -> list[Compartment]:
        """Fetch compartment fill levels for one machine."""
        data = await self._get_data(
            f"/{tokens.uuid}/locations/rvms/{rvm_id}/bin-status", tokens
        )
        try:
            return [parse_compartment(record) for record in data]
        except (KeyError, TypeError, ValueError) as err:
            raise RvmConnectionError("unexpected response") from err

    async def geocode(self, postcode: str) -> tuple[float, float, str]:
        """Resolve a postcode to (lat, lng, address) via OneMap."""
        body = await self._get_json(ONEMAP_URL.format(postcode=postcode), None)
        try:
            hit = body["results"][0]
            return float(hit["LATITUDE"]), float(hit["LONGITUDE"]), hit["ADDRESS"]
        except IndexError as err:
            raise RvmPostcodeNotFoundError(postcode) from err
        except (KeyError, TypeError, ValueError) as err:
            raise RvmConnectionError("unexpected response") from err

    async def close(self) -> None:
        """Close the underlying session."""
        await self._session.close()
