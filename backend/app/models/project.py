"""Projects and the tasks on their board.

A project belongs to a workspace: it is a piece of work the team is doing.
It carries a name, what it is for, what it delivers, and the room where it
is talked about — so a project is never a separate place, it is another way
of looking at the same team.

Its board holds tasks in four columns: 요청 → 할 일 → 진행 중 → 완료.
The order inside a column is kept by ``position``; a task that moves to
another column is placed at the end of it unless a place is named.

A project may carry several roadmaps — the lanes of work it is planned in,
one per tab — and a task is pinned to at most one of them.

It may also carry several milestones — the dated, coloured markers of what
is to be delivered — and a task belongs to at most one of them. A milestone
is not a roadmap: the roadmap says *where* the work is planned, the
milestone says *when* it is to be delivered.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

STATUS_REQUEST = "request"
STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in-progress"
STATUS_DONE = "done"
TASK_STATUSES = (STATUS_REQUEST, STATUS_TODO, STATUS_IN_PROGRESS, STATUS_DONE)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # What the project is about, in the words of the team doing it.
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    deliverables: Mapped[str] = mapped_column(Text, default="")
    channel_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    roadmaps: Mapped[list[Roadmap]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    """The people a project belongs to.

    The roster is what makes a project *mine*: a project with nobody on it
    is nobody's project, and one you are on is yours to look after.
    """

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="members")


class Milestone(Base):
    """A dated deliverable inside a project.

    A milestone is a marker of what is to be delivered and by when: it has a
    title, a start and an end, a colour of its own and the cards that
    deliver it. When it holds cards, its progress is their progress — the
    share of them that is done; with no cards the progress is what the team
    wrote down by hand.
    """

    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    start_at: Mapped[datetime] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime)
    color: Mapped[str] = mapped_column(String(16), default="#4f6cff")
    # The progress written by hand. It shows only while the milestone holds
    # no cards of its own.
    progress: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="milestones")


class Roadmap(Base):
    """A lane of work inside a project.

    A roadmap is a tab on the board: a project may have several of them,
    each holding the tasks planned for one period or one theme. A task
    belongs to at most one roadmap.
    """

    __tablename__ = "roadmaps"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="roadmaps")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default=STATUS_TODO, index=True)
    assignee_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The roadmap this task is planned in. The link is cut when the roadmap
    # goes away — the task itself stays on the board.
    roadmap_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("roadmaps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The milestone this task delivers. The link is cut when the milestone
    # goes away — the task itself stays on the board.
    milestone_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("milestones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="tasks")
    comments: Mapped[list[TaskComment]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskComment(Base):
    """A word about a task — the conversation that lives on the card."""

    __tablename__ = "task_comments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(40), ForeignKey("users.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    task: Mapped[Task] = relationship(back_populates="comments")
