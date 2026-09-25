"""The suite must never touch the production Redis, and live subscriptions must not leak.

- conftest.py points REDIS_URL at nothing, so the app runs on its in-memory mock.
- Each WebSocket viewer gets its own pub/sub subscription, released as soon as the viewer leaves —
  not at the next update, which during a quiet spell (or a parked Live page) may never come.
"""
import asyncio

from fastapi.testclient import TestClient

import api.main as main
from api.main import app
from services.mock_redis_service import MockRedisService
from services.redis_service import RedisService


def test_the_app_under_test_uses_the_in_memory_redis_mock():
    with TestClient(app) as client:
        assert isinstance(main.redis_service, MockRedisService)
        assert client.get("/health").json()["checks"]["redis"]["kind"] == "mock"


def test_a_websocket_viewer_is_unsubscribed_as_soon_as_it_disconnects():
    channel = "race:2024_Leave:updates"
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live/2024_Leave"):
            pass  # connect, then leave without any update ever being published

        for _ in range(40):                    # the server handles the close asynchronously
            if not main.redis_service.subscribers.get(channel):
                break
            client.portal.call(asyncio.sleep, 0.05)
        assert main.redis_service.subscribers.get(channel) == []


def test_updates_still_reach_a_connected_viewer():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live/2024_Updates") as ws:
            client.post("/simulate/live/2024_Updates")
            msg = ws.receive_json()

    assert msg["type"] == "update" and msg["data"]["positions"]


class FakePubSub:
    def __init__(self):
        self.channels, self.was_reset = [], False
        self._inbox: asyncio.Queue = asyncio.Queue()

    async def subscribe(self, channel):
        self.channels.append(channel)
        await self._inbox.put({"type": "message", "data": '{"n": 1}'})

    async def listen(self):
        while True:
            yield await self._inbox.get()

    async def reset(self):
        self.was_reset = True


class FakeRedisClient:
    def __init__(self):
        self.made = []

    def pubsub(self):
        self.made.append(FakePubSub())
        return self.made[-1]


def test_real_redis_gives_each_subscriber_its_own_pubsub_and_releases_it():
    async def scenario():
        svc = RedisService("redis://unused")
        svc.redis_client = FakeRedisClient()

        first, second = svc.subscribe_to_race("2024_A"), svc.subscribe_to_race("2024_B")
        assert await first.__anext__() == {"n": 1}
        assert await second.__anext__() == {"n": 1}

        a, b = svc.redis_client.made
        assert a is not b                                   # one connection per viewer
        assert a.channels == ["race:2024_A:updates"] and b.channels == ["race:2024_B:updates"]

        await first.aclose()                                 # the viewer left
        assert a.was_reset and not b.was_reset
        await second.aclose()
        assert b.was_reset

    asyncio.run(scenario())
