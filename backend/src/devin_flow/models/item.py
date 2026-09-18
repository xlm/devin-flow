from sqlmodel import Field, SQLModel


class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)


class ItemCreate(SQLModel):
    name: str


class ItemRead(SQLModel):
    id: int
    name: str
