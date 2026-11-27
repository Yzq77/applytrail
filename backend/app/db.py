from collections.abc import Iterator
from datetime import date

from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import db_path

_engine: Engine | None = None


def add_missing_columns(engine: Engine) -> list[str]:
    """Lightweight forward migration: add columns that newer versions introduced.

    ``create_all`` creates missing tables but never alters existing ones, so a database
    made by an older version would otherwise break when a field is added.
    """
    added = []
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                default = getattr(column.server_default, "arg", None)
                if isinstance(default, str):
                    ddl += " DEFAULT '" + default.replace("'", "''") + "'"
                conn.execute(text(ddl))
                added.append(f"{table.name}.{column.name}")
    return added


def make_engine(url: str, **kwargs) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False}, **kwargs)
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = make_engine(f"sqlite:///{path}")
    return _engine


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def get_today() -> date:
    """Injected so tests can freeze the clock."""
    return date.today()
