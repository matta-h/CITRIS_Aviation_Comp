"""
step1_time_model.py

Step 1 for the CITRIS Aviation routing simulator:
a historical replay time model that simulates "real-time in the past".

What this file gives you:
- A SimulationClock with fixed-size time steps
- A TimeWindowView that splits data into:
    * known data   -> timestamps <= current simulation time
    * hidden data  -> timestamps >  current simulation time
- A ReplayStore for timestamped records from any source
- Small helper functions and an example main() you can run now

This is intentionally backend-only and UI-agnostic.
You can plug it into FastAPI later, or call it from your route engine.

Python: 3.10+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


def ensure_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso_utc(value: str) -> datetime:
    """
    Parse ISO-8601 strings into timezone-aware UTC datetimes.

    Accepts strings like:
    - 2026-04-05T12:00:00Z
    - 2026-04-05T12:00:00+00:00
    """
    value = value.strip().replace("Z", "+00:00")
    return ensure_utc(datetime.fromisoformat(value))


@dataclass(order=True, frozen=True)
class TimedRecord:
    """
    Generic timestamped record for replay data.

    Example payloads:
    - weather snapshot
    - aircraft state
    - demand event
    - airport status
    """
    time: datetime
    source: str
    payload: Dict[str, Any]


@dataclass
class ReplayStore:
    """
    Sorted store for timestamped records.

    You can keep one ReplayStore per data type:
    - weather_store
    - traffic_store
    - demand_store

    Or merge them into one larger store if you prefer.
    """
    records: List[TimedRecord] = field(default_factory=list)

    def add(self, record: TimedRecord) -> None:
        self.records.append(
            TimedRecord(
                time=ensure_utc(record.time),
                source=record.source,
                payload=record.payload,
            )
        )
        self.records.sort(key=lambda r: r.time)

    def extend(self, records: Iterable[TimedRecord]) -> None:
        for record in records:
            self.add(record)

    def is_empty(self) -> bool:
        return len(self.records) == 0

    def start_time(self) -> Optional[datetime]:
        return self.records[0].time if self.records else None

    def end_time(self) -> Optional[datetime]:
        return self.records[-1].time if self.records else None

    def known_as_of(self, sim_time: datetime) -> List[TimedRecord]:
        """
        Returns all records the simulator is allowed to know at sim_time.
        """
        sim_time = ensure_utc(sim_time)
        return [r for r in self.records if r.time <= sim_time]

    def hidden_as_of(self, sim_time: datetime) -> List[TimedRecord]:
        """
        Returns all future records hidden from the simulator at sim_time.
        """
        sim_time = ensure_utc(sim_time)
        return [r for r in self.records if r.time > sim_time]

    def window(
        self,
        start: datetime,
        end: datetime,
        include_end: bool = True,
    ) -> List[TimedRecord]:
        """
        Returns records within [start, end] by default.
        If include_end=False, returns [start, end).
        """
        start = ensure_utc(start)
        end = ensure_utc(end)

        if include_end:
            return [r for r in self.records if start <= r.time <= end]
        return [r for r in self.records if start <= r.time < end]


@dataclass
class TimeWindowView:
    """
    Read-only snapshot of what is known vs hidden at a simulation instant.
    """
    current_time: datetime
    known_records: Sequence[TimedRecord]
    hidden_records: Sequence[TimedRecord]

    @property
    def known_count(self) -> int:
        return len(self.known_records)

    @property
    def hidden_count(self) -> int:
        return len(self.hidden_records)


@dataclass
class SimulationClock:
    """
    Simulation clock for historical replay.

    Concept:
    - The clock moves forward in fixed steps.
    - At each step, only data at or before current_time is visible.
    - Future data remains hidden until the clock advances.

    Example:
        clock = SimulationClock(
            start_time=parse_iso_utc("2026-04-05T15:00:00Z"),
            end_time=parse_iso_utc("2026-04-05T16:00:00Z"),
            step=timedelta(minutes=5),
        )
    """
    start_time: datetime
    end_time: datetime
    step: timedelta
    current_time: datetime = field(init=False)
    tick_index: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.start_time = ensure_utc(self.start_time)
        self.end_time = ensure_utc(self.end_time)

        if self.end_time < self.start_time:
            raise ValueError("end_time must be greater than or equal to start_time")

        if self.step.total_seconds() <= 0:
            raise ValueError("step must be positive")

        self.current_time = self.start_time

    def reset(self) -> None:
        self.current_time = self.start_time
        self.tick_index = 0

    def is_finished(self) -> bool:
        return self.current_time > self.end_time

    def can_advance(self) -> bool:
        return self.current_time + self.step <= self.end_time

    def advance(self) -> None:
        """
        Move forward by one time step.

        Note:
        Once current_time passes end_time, is_finished() becomes True.
        """
        if self.is_finished():
            return

        self.current_time += self.step
        self.tick_index += 1

    def progress_ratio(self) -> float:
        total = (self.end_time - self.start_time).total_seconds()
        if total == 0:
            return 1.0
        elapsed = min(
            max((self.current_time - self.start_time).total_seconds(), 0.0),
            total,
        )
        return elapsed / total

    def state_dict(self) -> Dict[str, Any]:
        return {
            "tick_index": self.tick_index,
            "current_time_iso": self.current_time.isoformat(),
            "start_time_iso": self.start_time.isoformat(),
            "end_time_iso": self.end_time.isoformat(),
            "step_seconds": self.step.total_seconds(),
            "progress_ratio": self.progress_ratio(),
        }

    def build_view(self, store: ReplayStore) -> TimeWindowView:
        now = self.current_time
        return TimeWindowView(
            current_time=now,
            known_records=store.known_as_of(now),
            hidden_records=store.hidden_as_of(now),
        )


def group_payloads_by_source(records: Sequence[TimedRecord]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convenience helper for turning a flat record list into source-grouped payloads.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record.source, []).append(record.payload)
    return grouped


def make_demo_store() -> ReplayStore:
    """
    Small self-contained demo dataset for testing Step 1 now.
    Replace this later with real adapter outputs from:
    - Open-Meteo
    - OpenSky / FR24 / simulated traffic
    - ForeFlight-derived events
    """
    store = ReplayStore()

    base = parse_iso_utc("2026-04-05T15:00:00Z")

    demo_records = [
        TimedRecord(
            time=base + timedelta(minutes=0),
            source="weather",
            payload={
                "airport": "KSQL",
                "severity": "good",
                "wind_speed_kt": 8,
                "visibility_m": 16000,
            },
        ),
        TimedRecord(
            time=base + timedelta(minutes=5),
            source="traffic",
            payload={
                "aircraft_id": "N123AB",
                "lat": 37.511,
                "lon": -122.250,
                "alt_ft": 1800,
                "velocity_kt": 120,
                "heading_deg": 145,
            },
        ),
        TimedRecord(
            time=base + timedelta(minutes=10),
            source="demand",
            payload={
                "origin": "UCM",
                "destination": "UCD",
                "passengers": 3,
            },
        ),
        TimedRecord(
            time=base + timedelta(minutes=15),
            source="weather",
            payload={
                "airport": "KLVK",
                "severity": "caution",
                "wind_speed_kt": 21,
                "visibility_m": 8000,
            },
        ),
    ]

    store.extend(demo_records)
    return store


def main() -> None:
    """
    Simple demo that prints what is known vs hidden at each simulation step.
    """
    store = make_demo_store()

    clock = SimulationClock(
        start_time=parse_iso_utc("2026-04-05T15:00:00Z"),
        end_time=parse_iso_utc("2026-04-05T15:20:00Z"),
        step=timedelta(minutes=5),
    )

    print("=== STEP 1 DEMO: Historical Replay Time Model ===")

    while not clock.is_finished():
        view = clock.build_view(store)

        print("\n----------------------------------------")
        print(f"Tick: {clock.tick_index}")
        print(f"Simulation time: {view.current_time.isoformat()}")
        print(f"Known records:  {view.known_count}")
        print(f"Hidden records: {view.hidden_count}")

        grouped = group_payloads_by_source(view.known_records)
        for source, payloads in grouped.items():
            print(f"  - {source}: {len(payloads)} known item(s)")

        clock.advance()

    print("\nDone.")


if __name__ == "__main__":
    main()
