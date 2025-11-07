import beanie.exceptions
import magic
import pyvips
from anyio import open_file
from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi_derive_responses import AutoDeriveResponsesAPIRoute
from starlette import status
from starlette.responses import StreamingResponse

import src.modules.clubs.crud as c
from src.api import docs
from src.api.dependencies import REQUIRE_ADMIN
from src.config import settings
from src.storages.mongo import Club

router = APIRouter(
    prefix="/clubs",
    tags=["Clubs"],
    route_class=AutoDeriveResponsesAPIRoute,
)
_description = """
Clubs list and management.
"""
docs.TAGS_INFO.append({"description": _description, "name": str(router.tags[0])})


@router.get(
    "/",
    responses={
        status.HTTP_200_OK: {"description": "List of clubs"},
    },
)
async def get_clubs_list() -> list[Club]:
    """Get list of clubs."""
    return await c.read_all()


@router.post(
    "/",
    responses={
        status.HTTP_201_CREATED: {"description": "New club is created"},
        status.HTTP_403_FORBIDDEN: {"description": "Only admin can create the club"},
    },
)
async def create_club(club_info: c.CreateClub, _: REQUIRE_ADMIN) -> Club:
    """Create a new club."""
    return await c.create(club_info)


@router.get(
    "/by-id/{id}",
    responses={
        status.HTTP_200_OK: {"description": "Club info"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def get_club_info(id: PydanticObjectId) -> Club:
    """Get club info."""
    club = await c.read(id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


@router.get(
    "/by-slug/{slug}",
    responses={
        status.HTTP_200_OK: {"description": "Club info"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def get_club_info_by_slug(slug: str) -> Club:
    """Get club info."""
    club = await c.read_by_slug(slug)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


@router.post(
    "/by-id/{id}",
    responses={
        status.HTTP_200_OK: {"description": "Changed club info successfully"},
        status.HTTP_403_FORBIDDEN: {"description": "Only admin can change club info"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def edit_club_info(id: PydanticObjectId, club_info: c.UpdateClub, _: REQUIRE_ADMIN) -> Club:
    """Edit a club info."""
    # TODO: Allow club leaders to edit some info
    club = await c.update(id, club_info)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


@router.post(
    "/by-slug/{slug}",
    responses={
        status.HTTP_200_OK: {"description": "Changed club info successfully"},
        status.HTTP_400_BAD_REQUEST: {"description": "Slug already exists"},
        status.HTTP_403_FORBIDDEN: {"description": "Only admin can change club info"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def edit_club_info_by_slug(slug: str, club_info: c.UpdateClub, _: REQUIRE_ADMIN) -> Club:
    """Edit a club info."""
    # TODO: Allow club leaders to edit some info
    club = await c.read_by_slug(slug)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    try:
        return await c.update(club.id, club_info)
    except beanie.exceptions.RevisionIdWasChanged:
        raise HTTPException(status_code=400, detail="Slug already exists")


@router.delete(
    "/by-id/{id}",
    responses={
        status.HTTP_200_OK: {"description": "Deleted club successfully"},
        status.HTTP_403_FORBIDDEN: {"description": "Only admin can delete the club"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def delete_club(id: PydanticObjectId, _: REQUIRE_ADMIN) -> None:
    """Delete a club."""
    result = c.delete(id)
    if not result:
        raise HTTPException(status_code=404, detail="Club not found")


@router.get(
    "/by-id/{id}/logo",
    responses={
        status.HTTP_200_OK: {"description": "Club info"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found or no logo available"},
    },
    response_model=None,
)
async def get_club_logo(id: str) -> StreamingResponse | None:
    """Get club info."""
    club = await c.read(id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    if not club.logo_file_id:
        raise HTTPException(status_code=404, detail="No logo available")

    file_path = settings.storage_path / club.logo_file_id
    async with await open_file(file_path, "rb") as f:
        return StreamingResponse(
            [await f.read()],
            media_type="image/webp",
            headers={"Content-Disposition": f"inline; filename={club.slug}.webp"},
        )


@router.post(
    "/by-id/{id}/logo",
    responses={
        status.HTTP_200_OK: {"description": "Changed club logo successfully"},
        status.HTTP_400_BAD_REQUEST: {"description": "Invalid content type"},
        status.HTTP_403_FORBIDDEN: {"description": "Only admin can change club logo"},
        status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
    },
)
async def set_club_logo(id: PydanticObjectId, logo_file: UploadFile, _: REQUIRE_ADMIN) -> Club:
    """Set a club logo picture."""
    # TODO: Allow club leaders to change logo
    club = await c.read(id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")

    bytes_ = await logo_file.read()
    content_type = logo_file.content_type
    if content_type is None:
        content_type = magic.Magic(mime=True).from_buffer(bytes_)

    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail=f"Invalid content type ({content_type})")

    # Convert to webp
    if content_type in ("image/jpeg", "image/png"):
        image = pyvips.Image.new_from_buffer(bytes_, "")
        bytes_ = image.write_to_buffer(".webp")

    # Save file
    logo_file_id = str(PydanticObjectId())
    file_path = settings.storage_path / logo_file_id
    async with await open_file(file_path, "wb") as buffer:
        await buffer.write(bytes_)

    club.logo_file_id = logo_file_id
    await club.save()
    return club
