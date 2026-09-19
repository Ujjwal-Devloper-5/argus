"""Initial database schema.

Revision ID: 0001
Revises: 
Create Date: 2026-09-19

Creates all core tables for Argus:
  - cameras
  - face_profiles
  - events
  - clips
  - unknown_face_trackers
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rtsp_url", sa.String(length=2048), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cameras_name", "cameras", ["name"], unique=True)

    op.create_table(
        "face_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("embeddings_json", sa.Text(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_trusted", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("face_profile_id", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("llm_analysis", sa.Text(), nullable=True),
        sa.Column("is_suspicious", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("thumbnail_path", sa.String(length=1024), nullable=True),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["face_profile_id"], ["face_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_camera_id", "events", ["camera_id"])
    op.create_index("ix_events_triggered_at", "events", ["triggered_at"])

    op.create_table(
        "clips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("local_path", sa.String(length=2048), nullable=False),
        sa.Column("remote_url", sa.String(length=2048), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clips_event_id", "clips", ["event_id"])

    op.create_table(
        "unknown_face_trackers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("face_hash", sa.String(length=64), nullable=False),
        sa.Column("appearance_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sample_thumbnail", sa.String(length=1024), nullable=True),
        sa.Column("prompted_user", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_unknown_face_trackers_face_hash", "unknown_face_trackers", ["face_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("unknown_face_trackers")
    op.drop_table("clips")
    op.drop_table("events")
    op.drop_table("face_profiles")
    op.drop_table("cameras")
