"""The node's declarative base.

Each service keeps its own metadata: the two schemas must never mix, or a migration check
would read the other service's tables as a difference. The pieces are shared (`service_kit.db`).
"""

from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from service_kit.db import NAMING_CONVENTION, TYPE_MAP, UuidPrimaryKey


class Base(UuidPrimaryKey, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: dict[Any, Any] = TYPE_MAP
