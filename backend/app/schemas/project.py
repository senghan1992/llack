"""Project and task schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import UserOut

TaskStatus = Literal["request", "todo", "in-progress", "done"]


class ProjectOut(ORMModel):
    id: str
    workspace_id: str
    name: str
    description: str = ""
    purpose: str = ""
    deliverables: str = ""
    channel_id: str | None = None
    created_by: str
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime
    members: list[UserOut] = []
    # Whether the caller is on the project's roster.
    is_member: bool = False
    # Tasks that are not finished yet, and how many of them are mine.
    open_tasks: int = 0
    my_open_tasks: int = 0
    # Every card on the project, and how many of them are done — the
    # progress the board header shows.
    total_tasks: int = 0
    done_tasks: int = 0
    # The period the project occupies: the first thing due to the last.
    # Nothing is due yet → no period.
    start_at: datetime | None = None
    end_at: datetime | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    purpose: str = Field(default="", max_length=2000)
    deliverables: str = Field(default="", max_length=2000)
    channel_id: str | None = None
    member_ids: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    purpose: str | None = Field(default=None, max_length=2000)
    deliverables: str | None = Field(default=None, max_length=2000)
    channel_id: str | None = None
    member_ids: list[str] | None = None
    is_archived: bool | None = None


class ProjectMemberAdd(BaseModel):
    user_id: str = Field(min_length=1)


class RoadmapOut(ORMModel):
    id: str
    project_id: str
    name: str
    position: int = 0
    created_by: str
    created_at: datetime
    # How many tasks are pinned to this roadmap, whatever their state.
    task_count: int = 0


class RoadmapUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class MilestoneOut(ORMModel):
    id: str
    project_id: str
    title: str
    start_at: datetime
    end_at: datetime
    color: str = "#4f6cff"
    # The progress that is shown: the cards' own progress when the
    # milestone holds cards, the one written by hand when it holds none.
    progress: int = 0
    # The progress the slider holds.
    manual_progress: int = 0
    description: str = ""
    # The cards that deliver this milestone.
    task_count: int = 0
    done_count: int = 0
    # Whether the progress is derived from those cards.
    auto_progress: bool = False
    task_ids: list[str] = []
    created_by: str
    created_at: datetime
    updated_at: datetime


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start_at: datetime
    end_at: datetime
    color: str = Field(default="#4f6cff", max_length=16)
    progress: int = Field(default=0, ge=0, le=100)
    description: str = Field(default="", max_length=4000)
    task_ids: list[str] = Field(default_factory=list)


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    start_at: datetime | None = None
    end_at: datetime | None = None
    color: str | None = Field(default=None, max_length=16)
    progress: int | None = Field(default=None, ge=0, le=100)
    description: str | None = Field(default=None, max_length=4000)
    task_ids: list[str] | None = None


class TaskCommentOut(ORMModel):
    id: str
    task_id: str
    user_id: str
    author: UserOut
    body: str
    created_at: datetime


class TaskOut(ORMModel):
    id: str
    project_id: str
    title: str
    description: str = ""
    status: str = "todo"
    assignee_id: str | None = None
    assignee: UserOut | None = None
    roadmap_id: str | None = None
    roadmap_name: str | None = None
    milestone_id: str | None = None
    milestone_name: str | None = None
    milestone_color: str | None = None
    created_by: str
    start_at: datetime | None = None
    due_at: datetime | None = None
    position: int = 0
    created_at: datetime
    updated_at: datetime
    comments: list[TaskCommentOut] = []
    comment_count: int = 0


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: TaskStatus = "todo"
    assignee_id: str | None = None
    roadmap_id: str | None = None
    milestone_id: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: TaskStatus | None = None
    assignee_id: str | None = None
    roadmap_id: str | None = None
    milestone_id: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    position: int | None = Field(default=None, ge=0)


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
