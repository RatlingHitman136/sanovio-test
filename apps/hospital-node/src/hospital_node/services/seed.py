"""Loads a demo dataset (ARCHITECTURE §21): users, templates, articles, then one
normalization pass over all articles."""

import json
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from hospital_node.core.db import Base
from hospital_node.core.settings import NodeSettings
from hospital_node.models import User
from hospital_node.models.users import Role
from hospital_node.services import articles, normalization, template_sync
from hospital_node.services.user_directory import create_user
from llm_client import LLMClient
from service_kit.security import PasswordHasher

DATASETS = ("demo_ksp", "demo_spital2")


class SeedUser(BaseModel):
    email: str
    display_name: str
    role: Role


class SeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedReport:
    users: int
    articles: int


def seed(
    session: Session,
    dataset: str,
    *,
    password: str,
    hasher: PasswordHasher,
    llm: LLMClient | None,
    settings: NodeSettings,
    now: datetime,
    reset: bool = False,
) -> SeedReport:
    if dataset not in DATASETS:
        raise SeedError(f"unknown dataset {dataset!r}; choose one of {', '.join(DATASETS)}")
    if session.scalar(select(User.id).limit(1)) is not None:
        if not reset:
            raise SeedError("the database already has data; pass reset to replace it")
        _wipe(session)

    users = TypeAdapter(list[SeedUser]).validate_python(_load(dataset, "users.json"))
    created = [
        create_user(
            session,
            hasher,
            email=user.email,
            password=password,
            role=user.role,
            display_name=user.display_name,
        )
        for user in users
    ]
    admin = next(user for user in created if user.role == Role.NODE_ADMIN)
    template_sync.store_seed(session, user_id=admin.id, now=now)
    templates = template_sync.installed(session)

    ingested = [
        articles.ingest(session, row, templates=templates, now=now)
        for row in _load(dataset, "articles.json")
    ]
    normalization.normalize(
        session, ingested, templates=templates, llm=llm, settings=settings, now=now
    )
    return SeedReport(users=len(created), articles=len(ingested))


def _load(dataset: str, name: str) -> Any:
    return json.loads((resources.files("hospital_node") / "seed" / dataset / name).read_text())


def _wipe(session: Session) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(delete(table))
    session.flush()
