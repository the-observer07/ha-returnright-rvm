"""Tests for models and status logic."""

from datetime import UTC, datetime

import pytest

from custom_components.returnright_rvm.models import (
    Compartment,
    busiest_fill,
    is_bin_full,
    normalise_status,
    parse_compartment,
    parse_machine,
)

RECORD = {
    "id": 1203,
    "locationName": "Cold Storage Serangoon Nex",
    "address": "23 Serangoon Central #B2-44/45 NEX, 556083",
    "postalCode": "556083",
    "latitude": "1.350819",
    "longitude": "103.872500",
    "status": "RUNNING",
    "rvm_remarks": "r",
    "rvmOpeningHours": "Mon - Sun:  24 Hrs",
    "distance": 321.03,
}


def _comp(fill: int) -> Compartment:
    return Compartment(type="CAN PET", fill_pct=fill, last_updated=None)


def test_parse_machine_maps_upstream_keys() -> None:
    machine = parse_machine(RECORD)
    assert machine.id == 1203
    assert machine.name == "Cold Storage Serangoon Nex"
    assert machine.postal_code == "556083"
    assert machine.lat == 1.350819
    assert machine.lng == 103.8725
    assert machine.distance_m == 321.03
    assert machine.raw_status == "RUNNING"
    assert machine.remarks == "r"
    assert machine.opening_hours == "Mon - Sun:  24 Hrs"


def test_parse_machine_strips_name_and_address() -> None:
    padded = {**RECORD, "locationName": "SHENG SIONG BLK 221 ", "address": " 221 Mount Vernon Rd "}
    machine = parse_machine(padded)
    assert machine.name == "SHENG SIONG BLK 221"
    assert machine.address == "221 Mount Vernon Rd"


def test_parse_machine_null_remarks_and_hours_become_empty_strings() -> None:
    nulls = {**RECORD, "rvm_remarks": None, "rvmOpeningHours": None}
    machine = parse_machine(nulls)
    assert machine.remarks == ""
    assert machine.opening_hours == ""

    absent = {k: v for k, v in RECORD.items() if k not in ("rvm_remarks", "rvmOpeningHours")}
    machine = parse_machine(absent)
    assert machine.remarks == ""
    assert machine.opening_hours == ""


def test_parse_compartment_reads_iso_utc_timestamp() -> None:
    comp = parse_compartment(
        {
            "compartment_type": "CAN PET",
            "threshold_level": 40,
            "last_updated": "2026-11-04T02:24:34.000Z",
        }
    )
    assert comp.type == "CAN PET"
    assert comp.fill_pct == 40
    assert comp.last_updated == datetime(2026, 11, 4, 2, 24, 34, tzinfo=UTC)

    for extra in ({"last_updated": None}, {}):
        comp = parse_compartment({"compartment_type": "CAN PET", "threshold_level": 40, **extra})
        assert comp.last_updated is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RUNNING", "running"),
        ("OPERATE", "running"),
        ("ONLINE", "running"),
        ("running", "running"),
        ("FULL", "full"),
        ("full", "full"),
        ("ERROR", "offline"),
        ("offline", "offline"),
        ("", "offline"),
        (None, "offline"),
        ("SOMETHING_NEW", "offline"),
    ],
)
def test_normalise_status(raw: str | None, expected: str) -> None:
    assert normalise_status(raw) == expected


def test_busiest_fill() -> None:
    assert busiest_fill([_comp(20), _comp(65)]) == 65
    assert busiest_fill([_comp(30)]) == 30
    assert busiest_fill([]) is None


@pytest.mark.parametrize(
    ("status", "fills", "expected"),
    [
        ("full", [20], True),
        ("running", [100], True),
        ("running", [99], False),
        ("running", [20, 100], True),
        ("offline", [], False),
        ("running", [], False),
    ],
)
def test_is_bin_full(status: str, fills: list[int], expected: bool) -> None:
    assert is_bin_full(status, [_comp(f) for f in fills]) is expected
