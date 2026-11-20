"""DDL SQL이 표 정의의 원본이다. autogenerate용 ORM 메타데이터는 두지 않는다."""

from alembic import context

from app.core.db import database_url, get_engine

if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
