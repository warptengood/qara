"""Tests for EventEngine — subscribe/publish and exception isolation."""

import pytest

from qara.core.event_engine import EventEngine
from qara.core.events import BaseEvent, ProcessFinished, ProcessStarted


@pytest.fixture
def engine() -> EventEngine:
    return EventEngine()


async def test_publish_delivers_to_subscriber(engine: EventEngine) -> None:
    received: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    engine.subscribe(handler)
    ev = ProcessStarted(pid=1, name="job")
    await engine.publish(ev)

    assert received == [ev]


async def test_publish_delivers_to_multiple_subscribers(engine: EventEngine) -> None:
    calls: list[str] = []

    async def h1(event: BaseEvent) -> None:
        calls.append("h1")

    async def h2(event: BaseEvent) -> None:
        calls.append("h2")

    engine.subscribe(h1)
    engine.subscribe(h2)
    await engine.publish(BaseEvent(pid=1, name="x"))

    assert calls == ["h1", "h2"]


async def test_faulty_handler_does_not_prevent_others(engine: EventEngine) -> None:
    """A handler that raises must not stop subsequent handlers from being called."""
    calls: list[str] = []

    async def bad_handler(event: BaseEvent) -> None:
        raise RuntimeError("boom")

    async def good_handler(event: BaseEvent) -> None:
        calls.append("ok")

    engine.subscribe(bad_handler)
    engine.subscribe(good_handler)

    # Should not raise
    await engine.publish(BaseEvent(pid=1, name="x"))

    assert calls == ["ok"]


async def test_publish_with_no_subscribers(engine: EventEngine) -> None:
    # Should complete without error
    await engine.publish(ProcessFinished(pid=1, name="job"))


async def test_subscribe_order_preserved(engine: EventEngine) -> None:
    order: list[int] = []

    for i in range(5):

        async def handler(event: BaseEvent, n: int = i) -> None:
            order.append(n)

        engine.subscribe(handler)

    await engine.publish(BaseEvent(pid=1, name="x"))
    assert order == [0, 1, 2, 3, 4]


async def test_handler_receives_correct_event_type(engine: EventEngine) -> None:
    received: list[BaseEvent] = []

    async def handler(event: BaseEvent) -> None:
        received.append(event)

    engine.subscribe(handler)
    crashed = ProcessFinished(pid=7, name="gpu_job", exit_code=0, duration_seconds=3.5)
    await engine.publish(crashed)

    assert len(received) == 1
    assert isinstance(received[0], ProcessFinished)
    assert received[0].exit_code == 0
