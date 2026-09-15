from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.production_db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

def database_url():
    # Keep Alembic on the same database URL as the application.
    url = os.environ.get("DATABASE_URL", "sqlite:///./trust_engine.db")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

url = database_url()
# Alembic's Config uses ConfigParser interpolation. PostgreSQL passwords can
# legitimately contain '%' characters, so escape them before storing the URL
# in the Alembic config. The actual SQLAlchemy URL remains unchanged.
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
