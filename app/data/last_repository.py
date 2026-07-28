import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_FILE = "lasts.json"


class LastRepository:
    """Library of shoe-last (колодка) 3D scans: manual metadata (article,
    size, fullness, model, material) plus measurements extracted once at
    upload time via stl_parser_service, so matching against a foot scan later
    doesn't need to re-parse the last's file.

    A production last is a graded family rather than a single object: model
    4977 exists in several sizes and several width grades, and each
    combination is its own scan. `article` names the family; `size` and
    `fullness` locate one last within it."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._file = file_path or DEFAULT_FILE
        self._data: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self._file):
            return []
        try:
            with open(self._file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self) -> None:
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def list(self) -> List[Dict[str, Any]]:
        return list(self._data)

    def get(self, last_id: str) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if item.get("id") == last_id:
                return item
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # One last = one canonical shape (a left last and a right last are
        # mirror-identical), so we store a single profile + summary, not both
        # feet; matching mirrors it to the foot's side when needed.
        record = {
            "id": uuid.uuid4().hex,
            "article": data.get("article", ""),
            "size": data.get("size", ""),
            # Width grade. Together with `size` this locates one last inside
            # its model family, which is how the library grid is laid out.
            "fullness": data.get("fullness", ""),
            "model": data.get("model", ""),
            "material": data.get("material", ""),
            "note": data.get("note", ""),
            "scan_file_url": data.get("scan_file_url", ""),
            "engine": data.get("engine", "slice_v1"),
            "side": data.get("side"),
            "length_mm": data.get("length_mm"),
            "width_mm": data.get("width_mm"),
            "height_mm": data.get("height_mm"),
            "ball_girth_mm": data.get("ball_girth_mm"),
            "instep_girth_mm": data.get("instep_girth_mm"),
            "ball_line_mm": data.get("ball_line_mm"),
            # Pose metadata for the hybrid_v2 pose model (stage 5 of the
            # slice_v1 -> hybrid_v2 migration) — optional; a foot isn't
            # re-posed at all unless both are set (see last_pose_service.py).
            "heel_height_mm": data.get("heel_height_mm"),
            "toe_spring_mm": data.get("toe_spring_mm"),
            "profile": data["profile"],
            "created_at": datetime.now().isoformat(),
        }
        self._data.append(record)
        self._save()
        return record

    # Metadata a user can fix after the fact without re-scanning the last --
    # everything the "add a last" form collects by hand, as opposed to what
    # stl_parser_service measured from the file (length_mm, ball_girth_mm,
    # profile, ...), which only a re-upload can change.
    _EDITABLE_FIELDS = (
        "article", "size", "fullness", "model", "material", "note", "side",
        "heel_height_mm", "toe_spring_mm",
    )

    def update(self, last_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for item in self._data:
            if item.get("id") == last_id:
                for field in self._EDITABLE_FIELDS:
                    if field in data:
                        item[field] = data[field]
                self._save()
                return item
        return None

    def set_scan_file_url(self, last_id: str, url: str) -> None:
        for item in self._data:
            if item.get("id") == last_id:
                item["scan_file_url"] = url
                self._save()
                return

    def delete(self, last_id: str) -> Optional[Dict[str, Any]]:
        for i, item in enumerate(self._data):
            if item.get("id") == last_id:
                removed = self._data.pop(i)
                self._save()
                return removed
        return None

    def rename_article(self, old_code: str, new_code: str) -> int:
        """Renaming an article number in the registry (LastArticleRepository)
        must not silently orphan every scan already filed under the old
        code -- they'd vanish from that model's group in the library grid.
        Returns how many records were updated."""
        old_code, new_code = (old_code or "").strip(), (new_code or "").strip()
        if old_code == new_code:
            return 0
        count = 0
        for item in self._data:
            if item.get("article") == old_code:
                item["article"] = new_code
                count += 1
        if count:
            self._save()
        return count
