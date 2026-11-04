"""Tests for the Return Right RVM coordinator."""

from datetime import timedelta

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.returnright_rvm.api import (
    RvmAuthError,
    RvmBlockedError,
    RvmConnectionError,
)
from custom_components.returnright_rvm.const import (
    CONF_SCAN_INTERVAL,
    DOMAIN,
    ISSUE_UPSTREAM_BLOCKED,
)
from custom_components.returnright_rvm.coordinator import RvmCoordinator, blocked_cycles

from .conftest import make_compartment, make_machine

A = (1.30, 103.80)
B = (1.35, 103.90)


def _spec(rvm_id, origin):
    return {
        "id": rvm_id,
        "name": f"RVM {rvm_id}",
        "lat": origin[0],
        "lng": origin[1],
        "radius": 2000,
    }


def _setup(hass, fake_client, make_entry, specs, options=None):
    entry = make_entry([_spec(i, o) for i, o in specs], options)
    entry.add_to_hass(hass)
    for i, o in specs:
        fake_client.nearby_results.setdefault(o, []).append(make_machine(i, o[0], o[1]))
        fake_client.bin_results[i] = [make_compartment()]
    return RvmCoordinator(hass, entry, fake_client)


async def test_success_returns_data_keyed_by_id(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, A)])
    data = await coord._async_update_data()
    assert set(data) == {1, 2}
    assert data[1].machine.id == 1
    assert data[1].compartments == (make_compartment(),)


async def test_tokens_fetched_once_per_cycle_for_many_machines(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, A), (3, B)])
    await coord._async_update_data()
    assert fake_client.tokens_calls == 1
    assert len(fake_client.bin_calls) == 3


async def test_machines_sharing_an_origin_share_one_nearby_call(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, A)])
    await coord._async_update_data()
    assert fake_client.nearby_calls == [(*A, 2000)]


async def test_distinct_origins_each_get_a_nearby_call(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, B)])
    await coord._async_update_data()
    assert sorted(fake_client.nearby_calls) == [(*A, 2000), (*B, 2000)]


async def test_one_bin_status_failure_drops_only_that_machine(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, A)])
    fake_client.bin_results[2] = RvmConnectionError("boom")
    data = await coord._async_update_data()
    assert set(data) == {1}


async def test_machine_missing_from_nearby_is_dropped_and_cycle_succeeds(
    hass, fake_client, make_entry
):
    coord = _setup(hass, fake_client, make_entry, [(1, A), (2, A)])
    fake_client.nearby_results[A] = [make_machine(1, *A)]
    data = await coord._async_update_data()
    assert set(data) == {1}
    assert fake_client.bin_calls == [1]


async def test_connection_error_raises_update_failed(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.tokens_result = RvmConnectionError("down")
    with pytest.raises(UpdateFailed) as err:
        await coord._async_update_data()
    assert err.value.translation_key == "cannot_connect"
    assert err.value.translation_domain == DOMAIN


async def test_auth_error_raises_update_failed(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.nearby_results[A] = RvmAuthError("nope")
    with pytest.raises(UpdateFailed) as err:
        await coord._async_update_data()
    assert err.value.translation_key == "auth_failed"


def _issue(hass):
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_UPSTREAM_BLOCKED)


async def test_blocked_three_cycles_creates_repair_issue(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(2):
        with pytest.raises(UpdateFailed) as err:
            await coord._async_update_data()
        assert err.value.translation_key == "upstream_blocked"
    assert _issue(hass) is None
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    issue = _issue(hass)
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == "upstream_blocked"


async def test_success_after_blocked_deletes_issue_and_resets_counter(
    hass, fake_client, make_entry
):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    ok_tokens = fake_client.tokens_result
    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(3):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    assert _issue(hass) is not None

    fake_client.tokens_result = ok_tokens
    await coord._async_update_data()
    assert _issue(hass) is None

    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(2):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    assert _issue(hass) is None


async def test_blocked_count_survives_coordinator_recreation(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(2):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    assert blocked_cycles(coord.config_entry.entry_id) == 2

    fresh = RvmCoordinator(hass, coord.config_entry, fake_client)
    with pytest.raises(UpdateFailed):
        await fresh._async_update_data()
    assert _issue(hass) is not None
    assert _issue(hass).is_persistent is True


async def test_non_blocked_failure_leaves_count_unchanged(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.tokens_result = RvmBlockedError("blocked")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    fake_client.tokens_result = RvmConnectionError("down")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert blocked_cycles(coord.config_entry.entry_id) == 1


async def test_success_resets_blocked_count(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    ok_tokens = fake_client.tokens_result
    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(3):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    fake_client.tokens_result = ok_tokens
    await coord._async_update_data()
    assert blocked_cycles(coord.config_entry.entry_id) == 0
    assert _issue(hass) is None


async def test_scan_interval_comes_from_options(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)], {CONF_SCAN_INTERVAL: 15})
    assert coord.update_interval == timedelta(minutes=15)


async def test_scan_interval_defaults_to_five_minutes(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    assert coord.update_interval == timedelta(minutes=5)


async def test_blocked_backs_off_doubling_up_to_cap(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)], {CONF_SCAN_INTERVAL: 1})
    fake_client.tokens_result = RvmBlockedError("blocked")
    seen = []
    for _ in range(6):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
        seen.append(coord.update_interval)
    assert seen == [timedelta(minutes=m) for m in (2, 4, 8, 15, 15, 15)]


async def test_backoff_never_goes_below_configured_interval(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)], {CONF_SCAN_INTERVAL: 30})
    fake_client.tokens_result = RvmBlockedError("blocked")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=30)


async def test_success_restores_configured_interval(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    ok_tokens = fake_client.tokens_result
    fake_client.tokens_result = RvmBlockedError("blocked")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=10)
    fake_client.tokens_result = ok_tokens
    await coord._async_update_data()
    assert coord.update_interval == timedelta(minutes=5)


async def test_recreated_coordinator_starts_backed_off(hass, fake_client, make_entry):
    coord = _setup(hass, fake_client, make_entry, [(1, A)])
    fake_client.tokens_result = RvmBlockedError("blocked")
    for _ in range(2):
        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
    fresh = RvmCoordinator(hass, coord.config_entry, fake_client)
    assert fresh.update_interval == timedelta(minutes=15)
