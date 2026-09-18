from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from devin_flow import db
from devin_flow.models import Item

SEED_ITEM_NAMES = ("alpha", "beta", "gamma")


def seed(session: Session) -> None:
    """Insert the seed rows that are missing. Safe to run repeatedly or concurrently.

    A unique violation means another seeder inserted a row between our select
    and commit, so roll back and re-check. Every retry sees strictly more rows.
    """
    while True:
        existing = set(
            session.exec(select(Item.name).where(col(Item.name).in_(SEED_ITEM_NAMES)))
        )
        missing = [name for name in SEED_ITEM_NAMES if name not in existing]
        if not missing:
            return
        session.add_all(Item(name=name) for name in missing)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            return


def main() -> None:
    with Session(db.get_engine()) as session:
        seed(session)


if __name__ == "__main__":
    main()
