from sqlmodel import Session, col, select

from devin_flow import db
from devin_flow.models import Item

SEED_ITEM_NAMES = ("alpha", "beta", "gamma")


def seed(session: Session) -> None:
    """Insert the seed rows that are missing. Safe to run repeatedly."""
    existing = set(
        session.exec(select(Item.name).where(col(Item.name).in_(SEED_ITEM_NAMES)))
    )
    session.add_all(Item(name=name) for name in SEED_ITEM_NAMES if name not in existing)
    session.commit()


def main() -> None:
    with Session(db.get_engine()) as session:
        seed(session)


if __name__ == "__main__":
    main()
