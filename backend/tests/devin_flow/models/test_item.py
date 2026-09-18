from sqlmodel import Session, SQLModel, select

from devin_flow.models import Item
from devin_flow.models.item import ItemRead


def test_item_table_is_registered_in_metadata() -> None:
    table = SQLModel.metadata.tables["item"]
    assert {column.name for column in table.columns} == {"id", "name"}
    assert table.columns["name"].unique


def test_item_roundtrip(unit_session: Session) -> None:
    unit_session.add(Item(name="widget"))
    unit_session.commit()
    stored = unit_session.exec(select(Item)).one()
    assert stored.id == 1
    assert ItemRead.model_validate(stored) == ItemRead(id=1, name="widget")
