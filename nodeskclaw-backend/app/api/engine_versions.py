"""Engine version catalog endpoints — read/write split for permission layering."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.engine_version import (
    EngineVersionCreate,
    EngineVersionInfo,
    EngineVersionUpdate,
)
from app.services import engine_version_service

engine_version_read_router = APIRouter()
engine_version_write_router = APIRouter()


@engine_version_read_router.get("", response_model=ApiResponse[list[EngineVersionInfo]])
async def list_versions(
    runtime: str = Query("openclaw"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    versions = await engine_version_service.list_published(runtime, db)
    return ApiResponse(data=[EngineVersionInfo.model_validate(v) for v in versions])


@engine_version_read_router.get("/default", response_model=ApiResponse[EngineVersionInfo | None])
async def get_default_version(
    runtime: str = Query("openclaw"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    ev = await engine_version_service.get_default(runtime, db)
    data = EngineVersionInfo.model_validate(ev) if ev else None
    return ApiResponse(data=data)


@engine_version_write_router.post("", response_model=ApiResponse[EngineVersionInfo])
async def publish_version(
    body: EngineVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ev = await engine_version_service.publish(
        runtime=body.runtime,
        version=body.version,
        image_tag=body.image_tag,
        release_notes=body.release_notes,
        user_id=user.id,
        db=db,
    )
    await db.commit()
    return ApiResponse(data=EngineVersionInfo.model_validate(ev))


@engine_version_write_router.patch("/{version_id}", response_model=ApiResponse[EngineVersionInfo])
async def update_version(
    version_id: str,
    body: EngineVersionUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if body.is_default is True:
        ev = await engine_version_service.set_default(version_id, db)
    elif body.status == "deprecated":
        ev = await engine_version_service.deprecate(version_id, db)
    elif body.release_notes is not None:
        ev = await engine_version_service.update_notes(version_id, body.release_notes, db)
    else:
        from app.core.exceptions import BadRequestError
        raise BadRequestError("无效的更新操作", "errors.engine_version.invalid_update")
    await db.commit()
    return ApiResponse(data=EngineVersionInfo.model_validate(ev))


@engine_version_write_router.delete("/{version_id}", response_model=ApiResponse[None])
async def delete_version(
    version_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    await engine_version_service.delete(version_id, db)
    await db.commit()
    return ApiResponse(data=None)
