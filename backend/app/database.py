from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

engine = create_engine(settings.app_database_url, pool_pre_ping=True)
# expire_on_commit=False: without it, accessing an attribute after commit()
# forces a fresh SELECT - but by then this request-scoped session's RLS
# transaction context (SET via set_config(..., is_local=true) in
# core.deps.set_tenant_context) has already ended with the commit, so that
# SELECT would be silently denied by row-level security. Postgres already
# returns server-generated defaults (id, created_at, ...) via implicit
# RETURNING during flush(), so nothing is lost by keeping the in-memory
# values instead of re-querying.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
