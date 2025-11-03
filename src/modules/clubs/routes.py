import magic
import pyvips
from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi_derive_responses import AutoDeriveResponsesAPIRoute
from starlette import status
from anyio import open_file
from starlette.responses import StreamingResponse

from src.api import docs
from src.api.dependencies import USER_AUTH
import src.modules.clubs.crud as c
import src.modules.users.crud as users_crud
from src.config import settings
from src.modules.inh_accounts_sdk import inh_accounts
from src.pydantic_base import BaseSchema
from src.storages.mongo import Club
from src.storages.mongo.user import UserRole

router = APIRouter(
    prefix="/clubs",
    tags=["Clubs"],
    route_class=AutoDeriveResponsesAPIRoute,
)
_description = """
Clubs list and management.
"""
docs.TAGS_INFO.append({"description": _description, "name": str(router.tags[0])})


@router.get("/", responses={
    status.HTTP_200_OK: {"description": "List of clubs"},
})
async def get_clubs_list() -> list[Club]:
    """Get list of clubs."""
    return await c.read_all()


@router.get("/{id}", responses={
    status.HTTP_200_OK: {"description": "Club info"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
})
async def get_club_info(id: str) -> Club:
    """Get club info."""
    club = await c.read(id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


class Leader(BaseSchema):
    """Club leader"""
    innohassle_id: str
    "ID of the InNoHassle Accounts user"
    name: str | None
    "Full name (or None if unknown)"
    email: str | None
    "Innomail (or None if unknown)"
    telegram_alias: str | None
    "Telegram alias (or None if unknown)"


@router.get("/{id}/leader", responses={
    status.HTTP_200_OK: {"description": "Club leader info"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
})
async def get_club_leader(id: PydanticObjectId, _: USER_AUTH) -> Leader | None:
    """Get club leader info."""
    club = await c.read(id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    
    leader_data = await inh_accounts.get_user(innohassle_id=club.leader_innohassle_id)
    if not leader_data:
        return None
    
    return Leader(
        innohassle_id=leader_data.id,
        name=leader_data.innopolis_sso.name if leader_data.innopolis_sso else None,
        email=leader_data.innopolis_sso.email if leader_data.innopolis_sso else None,
        telegram_alias=leader_data.telegram.username if leader_data.telegram else None,
    )
    


@router.post("/", responses={
    status.HTTP_201_CREATED: {"description": "New club is created"},
    status.HTTP_403_FORBIDDEN: {"description": "Only admin can create the club"},
})
async def create_club(club_info: c.CreateClub, current_user: USER_AUTH) -> Club:
    """Create a new club."""
    user = await users_crud.read_by_innohassle_id(current_user.innohassle_id)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You are not an admin")
    
    club = await c.create(club_info)
    return club


@router.delete("/{id}", responses={
    status.HTTP_200_OK: {"description": "Deleted club successfully"},
    status.HTTP_403_FORBIDDEN: {"description": "Only admin can delete the club"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
})
async def delete_club(id: PydanticObjectId, current_user: USER_AUTH) -> None:
    """Delete a club."""
    user = await users_crud.read_by_innohassle_id(current_user.innohassle_id)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You are not an admin")

    result = c.delete(id)
    if not result:
        raise HTTPException(status_code=404, detail="Club not found")


@router.post("/{id}", responses={
    status.HTTP_200_OK: {"description": "Changed club info successfully"},
    status.HTTP_403_FORBIDDEN: {"description": "Only admin can change club info"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
})
async def edit_club_info(id: PydanticObjectId, club_info: c.UpdateClub, current_user: USER_AUTH) -> Club:
    """Edit a club info."""
    # TODO: Allow club leaders to edit some info
    user = await users_crud.read_by_innohassle_id(current_user.innohassle_id)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You are not an admin")

    club = await c.update(id, club_info)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


@router.get("/{id}/logo", responses={
    status.HTTP_200_OK: {"description": "Club info"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
}, response_model=None)
async def get_club_logo(id: str) -> StreamingResponse | None:
    """Get club info."""
    club = await c.read(id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    
    if not club.logo_file_id:
        return None
    
    file_path = settings.storage_path / club.logo_file_id
    async with await open_file(file_path, "rb") as f:
        return StreamingResponse(
            [await f.read()],
            media_type="image/webp",
            headers={"Content-Disposition": f"inline; filename={club.slug}.webp"},
        )


@router.post("/{id}/logo", responses={
    status.HTTP_200_OK: {"description": "Changed club logo successfully"},
    status.HTTP_400_BAD_REQUEST: {"description": "Invalid content type"},
    status.HTTP_403_FORBIDDEN: {"description": "Only admin can change club logo"},
    status.HTTP_404_NOT_FOUND: {"description": "Club not found"},
})
async def set_club_logo(id: PydanticObjectId, logo_file: UploadFile, current_user: USER_AUTH) -> Club:
    """Set a club logo picture."""
    # TODO: Allow club leaders to change logo
    user = await users_crud.read_by_innohassle_id(current_user.innohassle_id)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You are not an admin")

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
