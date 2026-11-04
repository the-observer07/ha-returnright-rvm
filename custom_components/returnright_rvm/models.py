"""Data models and status logic for the Return Right RVM integration."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .const import STATUS_FULL, STATUS_OFFLINE, STATUS_RUNNING

_RUNNING_VALUES = {"RUNNING", "OPERATE", "ONLINE"}


@dataclass(frozen=True, slots=True)
class Compartment:
    """One bin compartment of a machine."""

    type: str
    fill_pct: int
    last_updated: datetime | None


@dataclass(frozen=True, slots=True)
class Machine:
    """A reverse vending machine."""

    id: int
    name: str
    address: str
    postal_code: str
    lat: float
    lng: float
    distance_m: float
    raw_status: str | None
    remarks: str
    opening_hours: str


@dataclass(frozen=True, slots=True)
class MachineData:
    """A machine together with its compartments."""

    machine: Machine
    compartments: tuple[Compartment, ...]


def parse_machine(record: dict[str, Any]) -> Machine:
    """Build a Machine from an upstream nearby record."""
    return Machine(
        id=record["id"],
        name=record["locationName"],
        address=record["address"],
        postal_code=record["postalCode"],
        lat=float(record["latitude"]),
        lng=float(record["longitude"]),
        distance_m=float(record["distance"]),
        raw_status=record.get("status"),
        remarks=record.get("rvm_remarks") or "",
        opening_hours=record.get("rvmOpeningHours") or "",
    )


def parse_compartment(record: dict[str, Any]) -> Compartment:
    """Build a Compartment from an upstream bin-status record."""
    updated = record.get("last_updated")
    return Compartment(
        type=record["compartment_type"],
        fill_pct=int(record["threshold_level"]),
        last_updated=datetime.fromisoformat(updated) if updated else None,
    )


def normalise_status(raw: str | None) -> str:
    """Map an upstream status string to running, full or offline."""
    value = (raw or "").upper()
    if value in _RUNNING_VALUES:
        return STATUS_RUNNING
    if value == "FULL":
        return STATUS_FULL
    return STATUS_OFFLINE


def busiest_fill(compartments: Iterable[Compartment]) -> int | None:
    """Return the highest fill percentage, or None without compartments."""
    return max((c.fill_pct for c in compartments), default=None)


def is_bin_full(status: str, compartments: Iterable[Compartment]) -> bool:
    """Return True if the machine is full or any compartment is at 100%."""
    fill = busiest_fill(compartments)
    return status == STATUS_FULL or (fill is not None and fill >= 100)
