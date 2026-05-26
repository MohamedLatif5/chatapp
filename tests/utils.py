import uuid as uuidlib


def unique_username() -> str:
    return "user_" + uuidlib.uuid4().hex[:10]


def unique_email(username: str) -> str:
    return f"{username}@test.com"


PASSWORD = "Passw0rd!23"


def register_payload(username: str | None = None) -> dict:
    username = username or unique_username()
    return {
        "username": username,
        "email": unique_email(username),
        "password": PASSWORD,
        "full_name": username.title(),
    }


def auth_header(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def ws_url(token: str) -> str:
    return f"/api/v1/ws?token={token}"
