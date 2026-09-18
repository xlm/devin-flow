from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from devin_flow import db
from devin_flow.models import Item

SEED_ITEM_NAMES = ("alpha", "beta", "gamma")


def seed(session: Session) -> None:
    """Insert the seed rows that are missing. Safe to run repeatedly or concurrently.

    Caller work already pending on the session is flushed first so its errors
    surface here. Each insert attempt runs in a savepoint: a unique violation
    means another seeder won the race, so only the attempt is rolled back and
    the missing set is re-read. Every retry sees strictly more rows.
    """
    session.flush()
    while True:
        existing = set(
            session.exec(select(Item.name).where(col(Item.name).in_(SEED_ITEM_NAMES)))
        )
        missing = [name for name in SEED_ITEM_NAMES if name not in existing]
        if not missing:
            break
        try:
            with session.begin_nested():
                session.add_all(Item(name=name) for name in missing)
        except IntegrityError:
            continue
        break
    session.commit()


def main() -> None:
    with Session(db.get_engine()) as session:
        seed(session)


if __name__ == "__main__":
    main()
