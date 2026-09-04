"""Types, parsing, hashing, and time-resolution transforms for NYC HVFHV."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

DATASET_ID = "u253-aew4"
DATASET_NAME = "2023 High Volume FHV Trip Data"
DOMAIN = "https://data.cityofnewyork.us"
TARGET = "shared_match_flag = 'Y'"
ROUNDING_MINUTES = 15
ROUNDING_HALF_MINUTES = 7.5
CERTIFIED = "OPTIMAL_NUMERICAL_MILP"
TIERS = (("same_od_zone", 0), ("same_pickup_zone", 1), ("provider_time_only", 2))
FIELDS = (
    "hvfhs_license_num",
    "request_datetime",
    "pickup_datetime",
    "dropoff_datetime",
    "pulocationid",
    "dolocationid",
    "trip_miles",
    "trip_time",
    "base_passenger_fare",
    "driver_pay",
    "shared_request_flag",
    "shared_match_flag",
)


class LiveDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class Trip:
    index: int
    provider: str
    role: str
    pickup: datetime | None
    dropoff: datetime | None
    pickup_zone: str | None
    dropoff_zone: str | None
    miles: float | None
    seconds: float | None
    fare: float | None
    driver_pay: float | None


@dataclass(frozen=True)
class ModelTrip:
    index: int
    provider: str
    role: str
    start: datetime | None
    end: datetime | None
    pickup_zone: str | None
    dropoff_zone: str | None
    miles: float | None
    seconds: float | None
    fare: float | None
    driver_pay: float | None


@dataclass(frozen=True)
class Bound:
    status: str
    value: float | None
    mip_gap: float | None
    residual: float | None


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    out = str(value).strip()
    return out or None


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        out = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if out.tzinfo is not None:
        out = out.astimezone(timezone.utc).replace(tzinfo=None)
    return out


def required_dt(value: str) -> datetime:
    out = dt(value)
    if out is None:
        raise argparse.ArgumentTypeError(f"invalid datetime: {value}")
    return out


def fmt(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat(timespec="seconds") + ".000"


def round15(value: datetime) -> datetime:
    origin = value.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = (value - origin).total_seconds()
    step = ROUNDING_MINUTES * 60
    return origin + timedelta(seconds=math.floor((seconds + step / 2) / step) * step)


def parse_trips(
    raw: Sequence[Mapping[str, Any]],
    provider: str,
    core_start: datetime,
    core_end: datetime,
) -> tuple[list[Trip], dict[str, Any]]:
    trips: list[Trip] = []
    issues = Counter()
    for index, row in enumerate(raw):
        row_provider = text(row.get("hvfhs_license_num")) or ""
        pickup = dt(row.get("pickup_datetime"))
        dropoff = dt(row.get("dropoff_datetime"))
        match = text(row.get("shared_match_flag"))
        if row_provider != provider:
            issues["wrong_provider"] += 1
        if match != "Y":
            issues["wrong_match_flag"] += 1
        if pickup is None or dropoff is None:
            issues["indeterminate_time"] += 1
        elif dropoff < pickup:
            issues["impossible_chronology"] += 1
        role = (
            "core"
            if row_provider == provider
            and match == "Y"
            and pickup is not None
            and core_start <= pickup < core_end
            else "buffer"
        )
        trips.append(
            Trip(
                index,
                row_provider,
                role,
                pickup,
                dropoff,
                text(row.get("pulocationid")),
                text(row.get("dolocationid")),
                number(row.get("trip_miles")),
                number(row.get("trip_time")),
                number(row.get("base_passenger_fare")),
                number(row.get("driver_pay")),
            )
        )
    audit = {
        "rows": len(trips),
        "core_rows": sum(trip.role == "core" for trip in trips),
        "buffer_rows": sum(trip.role == "buffer" for trip in trips),
        "issues": dict(issues),
        "completeness": {
            "pickup_zone": sum(trip.pickup_zone is not None for trip in trips),
            "dropoff_zone": sum(trip.dropoff_zone is not None for trip in trips),
            "trip_miles": sum(trip.miles is not None for trip in trips),
            "trip_time": sum(trip.seconds is not None for trip in trips),
            "base_passenger_fare": sum(trip.fare is not None for trip in trips),
            "driver_pay": sum(trip.driver_pay is not None for trip in trips),
        },
    }
    if (
        issues.get("wrong_provider")
        or issues.get("wrong_match_flag")
        or issues.get("impossible_chronology")
    ):
        raise LiveDataError(f"candidate row integrity failed: {dict(issues)}")
    return trips, audit


def model_rows(trips: Sequence[Trip], resolution: str) -> list[ModelTrip]:
    output: list[ModelTrip] = []
    for trip in trips:
        if trip.pickup is None or trip.dropoff is None:
            start = end = None
        elif resolution == "exact_second":
            start, end = trip.pickup, trip.dropoff
        elif resolution == "rounded_15m_outer":
            start = round15(trip.pickup) - timedelta(minutes=ROUNDING_HALF_MINUTES)
            end = round15(trip.dropoff) + timedelta(minutes=ROUNDING_HALF_MINUTES)
        else:
            raise ValueError(resolution)
        output.append(
            ModelTrip(
                trip.index,
                trip.provider,
                trip.role,
                start,
                end,
                trip.pickup_zone,
                trip.dropoff_zone,
                trip.miles,
                trip.seconds,
                trip.fare,
                trip.driver_pay,
            )
        )
    return output
