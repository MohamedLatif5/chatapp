# ChatApp

A real-time chat application backend built with FastAPI, native WebSockets, Redis, and PostgreSQL. It supports direct and group conversations, live message delivery, typing indicators, presence tracking, message search, and file uploads.

## Features

- **Authentication** - register, login (OAuth2 password flow), JWT access tokens with refresh token rotation
- **Conversations** - direct messages (get-or-create) and group chats with admin/member roles
- **Messages** - cursor-based pagination, replies, editing, soft delete, read receipts
- **Real-time layer** - native WebSocket endpoint with token auth, Redis Pub/Sub fan-out (multi-instance ready), typing indicators, presence with TTL-based online status
- **Search** - full message search scoped to the user's conversations
- **Uploads** - validated file uploads served through a static mount
- **Tests** - 31 integration and end-to-end tests running against real PostgreSQL and Redis

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn (ASGI) |
| Validation | Pydantic v2 + pydantic-settings |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) + Alembic |
| Real-time | WebSockets + Redis Pub/Sub |
| Presence | Redis sorted sets with TTL refresh |
| Auth | PyJWT + bcrypt |
| Testing | pytest + pytest-asyncio + httpx |
| Deployment | Docker + Docker Compose |

## Architecture

```
Client (WS/REST) ──► FastAPI ──► Redis Pub/Sub ──► FastAPI (any instance)
                      │                │                  │
                      ▼                │                  ▼
                 PostgreSQL ◄──────────┘           WebSocket clients
```

Every event (new/edited/deleted message, typing, presence) is published to Redis with an explicit recipient list. Each application instance subscribes to `chat:*` and delivers events only to locally connected sockets, so the real-time layer scales horizontally without sticky sessions.

## Quick Start

```bash
docker compose up --build
```

The API is now available at `http://localhost:8000` with interactive docs at `/docs`.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

PostgreSQL and Redis can be started separately with `docker compose up postgres redis`.

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account, returns token pair |
| POST | `/api/v1/auth/login` | OAuth2 form login |
| POST | `/api/v1/auth/refresh` | Rotate refresh token |
| GET | `/api/v1/users/me` | Current profile |
| GET | `/api/v1/users?q=` | Search users |
| GET | `/api/v1/users/{id}` | Profile with online status |
| POST | `/api/v1/conversations/dm` | Get or create direct message |
| POST | `/api/v1/conversations/group` | Create group |
| GET | `/api/v1/conversations` | List with unread counts and last message |
| POST | `/api/v1/conversations/{id}/messages` | Send message |
| GET | `/api/v1/conversations/{id}/messages` | Cursor pagination (`before_id`, `limit`) |
| POST | `/api/v1/conversations/{id}/read` | Mark read, broadcasts receipt |
| PATCH | `/api/v1/messages/{id}` | Edit own message |
| DELETE | `/api/v1/messages/{id}` | Soft delete |
| GET | `/api/v1/search/messages?q=` | Search in user's conversations |
| POST | `/api/v1/uploads` | Upload file |

## WebSocket Protocol

Connect to `/api/v1/ws?token=<access_token>`. Clients send JSON events and receive broadcast events:

```json
{"type": "ping"}                     -> {"type": "pong"} (refreshes presence TTL)
{"type": "typing", "conversation_id": "..."}
{"type": "message", "conversation_id": "...", "content": "hello"}
```

Server events: `message.new`, `message.updated`, `message.deleted`, `message.read`, `typing`, `user.online`, `user.offline`.

## Testing

```bash
docker compose up -d postgres redis
pytest tests
```

The suite runs against a real PostgreSQL database and Redis instance, covering auth, conversations, message flows, pagination, search, WebSocket delivery, and a full end-to-end chat journey.

## Project Structure

```
app/
├── api/          # REST + WebSocket endpoints, dependencies
├── core/         # settings, security (JWT, bcrypt)
├── db/           # async engine, session, declarative base
├── models/       # SQLAlchemy models (User, Conversation, Message)
├── schemas/      # Pydantic request/response models
└── services/     # business logic + realtime broker
alembic/          # migrations
tests/            # integration + e2e tests
```
