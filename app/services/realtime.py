import uuid

from fastapi import WebSocket


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
        import json

        if not user_ids:
            return
        text = json.dumps(payload, default=str)
        for user_id in set(user_ids):
            for websocket in list(self.connections.get(user_id, ())):
                try:
                    await websocket.send_text(text)
                except Exception:
                    self.disconnect(websocket, user_id)
