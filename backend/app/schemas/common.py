"""Shared schema pieces."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for schemas that are built from ORM instances."""

    model_config = ConfigDict(from_attributes=True)
