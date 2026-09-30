"""
Argus Kafka Topic Registry.

Single source of truth for all Kafka topic names.
Never use raw strings for topics anywhere else in the codebase — always import from here.
"""
from __future__ import annotations

from enum import StrEnum


class ArgusTopics(StrEnum):
    """All Kafka topics used by the Argus system."""

    # Phase 7: Cloud upload jobs — clip paths published here after recording
    UPLOADS = "argus.uploads"

    # Phase 8: Raw decoded frames from stream workers → detect worker pool
    FRAMES = "argus.frames"

    # Phase 8: Completed security events → alert/db/dashboard consumer groups
    EVENTS = "argus.events"

    # Phase 8: AutoLearner face prompts → deduplicated by face_hash key
    LEARN = "argus.learn"

    # Dead letter queue — messages that failed all retries land here
    DLQ = "argus.dlq"


# Consumer group IDs — one per independent downstream consumer
class ArgusConsumerGroups(StrEnum):
    STORAGE_WORKERS = "argus-storage-workers"
    ALERTS = "argus-alerts"
    DATABASE = "argus-db"
    DASHBOARD = "argus-dashboard"
    LEARN_PROMPT = "argus-learn-prompt"
