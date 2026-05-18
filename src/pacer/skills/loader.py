from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

_FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


@dataclass
class SkillMeta:
    name: str
    subject: str
    chapter: str
    description: str
    path: Path


class SkillsLoader:
    """Lazy filesystem-backed skills. content/<subject>/<name>.md"""

    def __init__(self, root: Path):
        self.root = root
        self._index: dict[str, SkillMeta] | None = None

    def _ensure_index(self) -> dict[str, SkillMeta]:
        if self._index is not None:
            return self._index
        index: dict[str, SkillMeta] = {}
        for path in self.root.rglob("*.md"):
            try:
                meta = self._parse_metadata(path)
                if meta is not None:
                    index[meta.name] = meta
            except Exception:
                continue
        self._index = index
        return index

    def _parse_metadata(self, path: Path) -> SkillMeta | None:
        text = path.read_text(encoding="utf-8")
        m = _FM_RE.match(text)
        if m is None:
            return None
        fm = m.group(1)
        data: dict[str, str] = {}
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
        if "name" not in data:
            return None
        return SkillMeta(
            name=data["name"],
            subject=data.get("subject", path.parent.name),
            chapter=data.get("chapter", ""),
            description=data.get("description", ""),
            path=path,
        )

    def list_skills(self, *, subject: str | None = None) -> list[SkillMeta]:
        idx = self._ensure_index()
        all_ = list(idx.values())
        if subject is None:
            return all_
        return [s for s in all_ if s.subject == subject]

    def load(self, name: str) -> str | None:
        idx = self._ensure_index()
        meta = idx.get(name)
        if meta is None:
            return None
        return meta.path.read_text(encoding="utf-8")
