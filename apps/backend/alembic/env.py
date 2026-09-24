from logging.config import fileConfig

from sqlalchemy import create_engine

from alembic import context
from rolewise import models  # noqa: F401  (registers tables on Base.metadata)
from rolewise.config import get_settings
from rolewise.db import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().sqlalchemy_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
