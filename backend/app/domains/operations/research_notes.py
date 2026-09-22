"""Research Notes & Annotations Tracker for Phase 10."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from app.domains.operations.models import ResearchNote
from app.domains.platform.logging import get_structured_logger

logger = get_structured_logger("operations.research_notes")
DEFAULT_NOTES_DIR = Path("scratch/research_notes")


class ResearchNotesEngine:
    """Manages markdown research notes attached to strategies, experiments, trading days, snapshots, reports, and version changes."""

    def __init__(self, notes_dir: Path = DEFAULT_NOTES_DIR) -> None:
        self.notes_dir = notes_dir
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self._notes: dict[str, ResearchNote] = {}
        self._lock = threading.Lock()
        self._load_persisted()

    def create_note(
        self,
        entity_type: str,
        entity_id: str,
        author: str,
        title: str,
        content_markdown: str,
        tags: list[str] | None = None,
    ) -> ResearchNote:
        """Attaches a new research note to a specific platform entity."""
        note = ResearchNote(
            entity_type=entity_type,
            entity_id=entity_id,
            author=author,
            title=title,
            content_markdown=content_markdown,
            tags=tags or [],
        )

        with self._lock:
            self._notes[note.note_id] = note
            self._persist_note(note)
            logger.info("research_note_created", note_id=note.note_id, entity_type=entity_type, entity_id=entity_id)

        return note

    def get_note(self, note_id: str) -> ResearchNote | None:
        with self._lock:
            return self._notes.get(note_id)

    def list_notes(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tag: str | None = None,
    ) -> list[ResearchNote]:
        with self._lock:
            res = list(self._notes.values())
            if entity_type:
                res = [n for n in res if n.entity_type == entity_type]
            if entity_id:
                res = [n for n in res if n.entity_id == entity_id]
            if tag:
                res = [n for n in res if tag in n.tags]
            return res

    def _persist_note(self, note: ResearchNote) -> None:
        filepath = self.notes_dir / f"note_{note.note_id}.json"
        filepath.write_text(note.model_dump_json(indent=2), encoding="utf-8")

    def _load_persisted(self) -> None:
        for file in self.notes_dir.glob("note_*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                note = ResearchNote(**data)
                self._notes[note.note_id] = note
            except Exception as exc:
                logger.warning("note_load_failed", file=str(file), error=str(exc))
