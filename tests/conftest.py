import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


from datetime import UTC, datetime  # noqa: E402

from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.returnright_rvm.api import Tokens  # noqa: E402
from custom_components.returnright_rvm.const import CONF_MACHINES, DOMAIN  # noqa: E402
from custom_components.returnright_rvm.models import Compartment, Machine  # noqa: E402


def make_machine(rvm_id: int, lat: float = 1.30, lng: float = 103.80) -> Machine:
    """Build a Machine for tests."""
    return Machine(
        id=rvm_id,
        name=f"RVM {rvm_id}",
        address="1 Test Road",
        postal_code="123456",
        lat=lat,
        lng=lng,
        distance_m=100.0,
        raw_status="RUNNING",
        remarks="",
        opening_hours="",
    )


def make_compartment(fill_pct: int = 40) -> Compartment:
    """Build a Compartment for tests."""
    return Compartment(type="CAN", fill_pct=fill_pct, last_updated=datetime(2026, 1, 1, tzinfo=UTC))


class FakeClient:
    """Scriptable stand-in for RvmClient that counts calls."""

    def __init__(self) -> None:
        self.tokens_result: Tokens | Exception = Tokens(uuid="u", token="t")
        self.nearby_results: dict[tuple[float, float], list[Machine] | Exception] = {}
        self.bin_results: dict[int, list[Compartment] | Exception] = {}
        self.tokens_calls = 0
        self.nearby_calls: list[tuple[float, float, int]] = []
        self.bin_calls: list[int] = []

    @staticmethod
    def _resolve(value):
        if isinstance(value, Exception):
            raise value
        return value

    async def get_tokens(self) -> Tokens:
        self.tokens_calls += 1
        return self._resolve(self.tokens_result)

    async def nearby(self, tokens, lat, lng, radius_m):
        self.nearby_calls.append((lat, lng, radius_m))
        return self._resolve(self.nearby_results[(lat, lng)])

    async def bin_status(self, tokens, rvm_id):
        self.bin_calls.append(rvm_id)
        return self._resolve(self.bin_results[rvm_id])


@pytest.fixture
def fake_client() -> FakeClient:
    """Return a fresh FakeClient."""
    return FakeClient()


@pytest.fixture
def make_entry():
    """Return a factory for a MockConfigEntry with configured machines."""

    def _make(machines: list[dict], options: dict | None = None) -> MockConfigEntry:
        return MockConfigEntry(
            domain=DOMAIN,
            data={CONF_MACHINES: machines},
            options=options or {},
        )

    return _make
