import asyncio

from src.modules.inh_accounts_sdk import inh_accounts
from src.pydantic_base import BaseSchema


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


async def read_by_innohassle_id(innohassle_id: str) -> Leader | None:
    leader_data = await inh_accounts.get_user(innohassle_id=innohassle_id)
    if not leader_data:
        return None

    return Leader(
        innohassle_id=leader_data.id,
        name=leader_data.innopolis_sso.name if leader_data.innopolis_sso else None,
        email=leader_data.innopolis_sso.email if leader_data.innopolis_sso else None,
        telegram_alias=leader_data.telegram.username if leader_data.telegram else None,
    )


async def read_many_by_innohassle_ids(innohassle_ids: list[str]) -> list[Leader | None]:
    user_info_tasks = [inh_accounts.get_user(innohassle_id=id) for id in innohassle_ids]
    user_infos = await asyncio.gather(*user_info_tasks, return_exceptions=True)

    leaders = []
    for user_info in user_infos:
        if not user_info or isinstance(user_info, BaseException):
            leaders.append(None)
            continue
        if not user_info.innopolis_sso:  # No info about leader
            leaders.append(None)
            continue
        leaders.append(
            Leader(
                innohassle_id=user_info.innopolis_sso.id,
                name=user_info.innopolis_sso.name,
                email=user_info.innopolis_sso.email,
                telegram_alias=user_info.telegram.username if user_info.telegram else None,
            )
        )
    return leaders
