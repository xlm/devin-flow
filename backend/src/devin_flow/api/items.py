from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from devin_flow.db import get_session
from devin_flow.models import Item
from devin_flow.models.item import ItemCreate, ItemRead

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class ConflictResponse(BaseModel):
    detail: str


@router.get("/items", response_model=list[ItemRead])
def list_items(session: SessionDep) -> Sequence[Item]:
    return session.exec(select(Item).order_by(col(Item.id))).all()


@router.post(
    "/items",
    response_model=ItemRead,
    status_code=201,
    responses={409: {"model": ConflictResponse, "description": "Name already taken"}},
)
def create_item(payload: ItemCreate, session: SessionDep) -> Item:
    item = Item.model_validate(payload)
    session.add(item)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, f"item {payload.name!r} already exists") from exc
    session.refresh(item)
    return item
