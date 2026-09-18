from sqlmodel import Field, SQLModel


class Item(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)


class ItemCreate(SQLModel):
    name: str = Field(
        min_length=1, max_length=255, schema_extra={"pattern": r"^[^\x00]*$"}
    )


class ItemRead(SQLModel):
    id: int
    name: str
