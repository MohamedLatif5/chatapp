import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models import User

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = set(settings.ALLOWED_UPLOAD_EXTENSIONS.split(","))
MAX_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _validate(file: UploadFile) -> str:
    extension = Path(file.filename or "").suffix.lower().lstrip(".")
    if not extension or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return extension


@router.post("")
async def upload_file(
    file: UploadFile,
    _: User = Depends(get_current_user),
) -> dict:
    extension = _validate(file)
    data = await file.read(MAX_SIZE_BYTES + 1)
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Max size: {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    group = uuid.uuid4().hex
    name = f"{uuid.uuid4().hex}.{extension}"
    directory = Path(settings.UPLOAD_DIR) / group
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)

    return {
        "url": f"/static/uploads/{group}/{name}",
        "filename": file.filename,
        "size": len(data),
        "content_type": file.content_type,
    }
