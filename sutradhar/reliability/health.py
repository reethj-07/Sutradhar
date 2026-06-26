"""Health registry (PRD §12 `/healthz` `/readyz`, §13).

Components register a name + async probe; the registry aggregates them for the
operator. `/healthz` => process is alive; `/readyz` => all critical probes pass.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum


class HealthState(StrEnum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class HealthStatus:
    name: str
    state: HealthState
    detail: str = ""


Probe = Callable[[], Awaitable[bool]]


class HealthRegistry:
    """Aggregates component health probes."""

    def __init__(self) -> None:
        self._probes: dict[str, tuple[Probe, bool]] = {}

    def register(self, name: str, probe: Probe, *, critical: bool = True) -> None:
        self._probes[name] = (probe, critical)

    async def check(self) -> list[HealthStatus]:
        async def run(name: str, probe: Probe) -> HealthStatus:
            try:
                ok = await asyncio.wait_for(probe(), timeout=2.0)
                return HealthStatus(name, HealthState.UP if ok else HealthState.DOWN)
            except Exception as exc:
                return HealthStatus(name, HealthState.DOWN, str(exc))

        return await asyncio.gather(*(run(n, p) for n, (p, _) in self._probes.items()))

    async def ready(self) -> bool:
        """True iff every *critical* probe is UP."""
        statuses = {s.name: s for s in await self.check()}
        return all(
            statuses[name].state is HealthState.UP
            for name, (_, critical) in self._probes.items()
            if critical
        )
