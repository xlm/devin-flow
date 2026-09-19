from sqlmodel import Session

from devin_flow import db


def seed(session: Session) -> None:
    """Bring the database to its seeded state. Safe to run repeatedly or concurrently.

    The seeded state is an empty Canvas, so there is nothing to insert yet.
    Caller work already pending on the session is committed so the seeded
    database is always in a consistent, committed state.
    """
    session.commit()


def main() -> None:
    with Session(db.get_engine()) as session:
        seed(session)


if __name__ == "__main__":
    main()
