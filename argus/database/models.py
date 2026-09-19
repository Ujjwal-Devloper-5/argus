"""
Argus Database Models — SQLAlchemy 2.0 style with fully typed Mapped columns.

All models use the new `Mapped[]` annotation syntax (no more `Column()` directly).
This gives full type-checker support and IDE autocomplete on model instances.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware). Preferred over datetime.utcnow()."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """All models inherit from this base."""
    pass


class Camera(Base):
    """
    Represents a configured RTSP camera.
    Created automatically from config.yaml on first startup.
    """

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    rtsp_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # Relationships
    events: Mapped[list[Event]] = relationship("Event", back_populates="camera", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Camera id={self.id} name={self.name!r} active={self.is_active}>"


class FaceProfile(Base):
    """
    A known person whose face has been enrolled.
    Multiple embeddings are stored per profile (one per training image)
    to improve match robustness across angles, lighting conditions.
    """

    __tablename__ = "face_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # JSON-serialized list of base64-encoded float32 numpy arrays
    # e.g.: ["base64_embed_1", "base64_embed_2", ...]
    embeddings_json: Mapped[str] = mapped_column(Text, nullable=False)
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # is_trusted=False: face is known but still triggers an alert (e.g., ex-employee)
    is_trusted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    events: Mapped[list[Event]] = relationship("Event", back_populates="face_profile")

    def get_embeddings(self) -> list[list[float]]:
        """Deserialize embeddings from JSON storage. Returns list of float lists."""
        import base64
        import struct
        raw = json.loads(self.embeddings_json)
        result = []
        for encoded in raw:
            data = base64.b64decode(encoded)
            n_floats = len(data) // 4  # float32 = 4 bytes
            floats = list(struct.unpack(f"{n_floats}f", data))
            result.append(floats)
        return result

    @staticmethod
    def serialize_embeddings(embeddings: list) -> str:
        """
        Serialize embedding arrays for DB storage.
        Accepts list of lists (plain Python) or numpy arrays.
        Uses struct for serialization — no numpy dependency in DB layer.
        """
        import base64
        import struct
        encoded = []
        for emb in embeddings:
            # Support both plain lists and numpy arrays
            try:
                floats = emb.tolist()  # numpy array
            except AttributeError:
                floats = list(emb)     # plain list
            data = struct.pack(f"{len(floats)}f", *floats)
            encoded.append(base64.b64encode(data).decode())
        return json.dumps(encoded)

    def __repr__(self) -> str:
        return f"<FaceProfile id={self.id} name={self.name!r} trusted={self.is_trusted}>"


class Event(Base):
    """
    A security event — triggered when an unknown or untrusted person is detected.
    One event per detection incident (a person appearing on camera).
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("cameras.id"), nullable=False, index=True)
    # None if the face was not recognized
    face_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("face_profiles.id"), nullable=True
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), index=True
    )
    # Raw LLM response text
    llm_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Path to the JPEG snapshot frame at moment of detection
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Cosine similarity score from face recognition (0.0–1.0)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    camera: Mapped[Camera] = relationship("Camera", back_populates="events")
    face_profile: Mapped[FaceProfile | None] = relationship("FaceProfile", back_populates="events")
    clips: Mapped[list[Clip]] = relationship("Clip", back_populates="event", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id} camera_id={self.camera_id} "
            f"suspicious={self.is_suspicious} at={self.triggered_at}>"
        )


class Clip(Base):
    """
    A video clip recorded for an event.
    Includes pre-event buffer + post-event recording.
    May have a remote URL once uploaded to cloud storage.
    """

    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=False, index=True
    )
    local_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    remote_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # Relationships
    event: Mapped[Event] = relationship("Event", back_populates="clips")

    def __repr__(self) -> str:
        return f"<Clip id={self.id} event_id={self.event_id} path={self.local_path!r}>"


class UnknownFaceTracker(Base):
    """
    Tracks appearances of unrecognized faces for the auto-learning system.

    When an unknown face appears repeatedly, Argus prompts the user via
    Telegram to either enroll them as a known person or mark them as ignored.
    """

    __tablename__ = "unknown_face_trackers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Deterministic hash of the face embedding centroid (rounded to 2 decimal places)
    # Prevents floating-point noise from creating duplicate tracker entries.
    face_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    appearance_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    # Path to the clearest captured face crop (used in Telegram approval prompt)
    sample_thumbnail: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Has a Telegram approval prompt already been sent for this face?
    prompted_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # User explicitly marked this face as "not a threat, but not enrolled"
    is_ignored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<UnknownFaceTracker hash={self.face_hash[:8]}... "
            f"count={self.appearance_count} prompted={self.prompted_user}>"
        )
