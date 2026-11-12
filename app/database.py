from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

class Base(DeclarativeBase):
    pass

# Khởi tạo session làm việc với database thông qua database_url
def make_session_factory(database_url: str, schema: str | None = None):
    connect_args = {"prepare_threshold": None}

    engine = create_engine(database_url, connect_args= connect_args,pool_pre_ping=True)
    if schema:
        engine = engine.execution_options(schema_translate_map={None: schema})
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
