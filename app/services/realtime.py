import asyncio
import json
import uuid

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.core.config import settings

CONVERSATION_CHANNEL_PREFIX = "chat:conversation:"
PRESENCE_CHANNEL = "chat:presence"


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, set[WebSocket]] = {}

    def connect(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        self.connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        sockets = self.connections.get(user_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                del self.connections[user_id]

    def is_connected_locally(self, user_id: uuid.UUID) -> bool:
        return bool(self.connections.get(user_id))

    async def send_to_users(self, user_ids, payload: dict) -> None:
        if not user_ids:
            return
        text = json.dumps(payload, default=str)
        for user_id in set(user_ids):
            for websocket in list(self.connections.get(user_id, ())):
                try:
                    await websocket.send_text(text)
                except Exception:
                    self.disconnect(websocket, user_id)


class RealtimeBroker:
    def __init__(self) -> None:
        self.manager = ConnectionManager()
        self.redis: aioredis.Redis | None = None
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        self._pubsub = self.redis.pubsub()
        await self._pubsub.psubscribe("chat:*")
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None
        if self.redis is not None:
            await self.redis.aclose()
            self.redis = None

    async def _listen(self) -> None:
        async for event in self._pubsub.listen():
            if event["type"] != "pmessage":
                continue
            try:
                payload = json.loads(event["data"])
                recipients = payload.pop("recipients", [])
                await self.manager.send_to_users(recipients, payload)
            except Exception:
                continue

    async def publish(self, channel: str, payload: dict, recipients) -> None:
        if self.redis is None:
            return
        data = {**payload, "recipients": [str(r) for r in recipients]}
        await self.redis.publish(channel, json.dumps(data, default=str))

    async def publish_to_conversation(
        self, conversation_id: uuid.UUID, payload: dict, recipients
    ) -> None:
        await self.publish(CONVERSATION_CHANNEL_PREFIX + str(conversation_id), payload, recipients)

    async def publish_presence(self, payload: dict, recipients) -> None:
        await self.publish(PRESENCE_CHANNEL, payload, recipients)


broker = RealtimeBroker()
