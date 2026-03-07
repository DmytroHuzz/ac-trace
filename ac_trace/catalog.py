from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml


class CatalogError(ValueError):
    """Raised when the acceptance-criteria catalog is invalid."""


@dataclass(frozen=True)
class CriterionDefinition:
    id: str
    title: str
    description: str


@dataclass(frozen=True)
class CriteriaCatalog:
    catalog_path: Path
    project_root: Path
    source_paths: list[str]
    test_paths: list[str]
    acceptance_criteria: list[CriterionDefinition]

    def find_criteria(self, ids: Optional[Iterable[str]] = None) -> list[CriterionDefinition]:
        if ids is None:
            return self.acceptance_criteria

        wanted = set(ids)
        selected = [criterion for criterion in self.acceptance_criteria if criterion.id in wanted]
        missing = wanted.difference({criterion.id for criterion in selected})
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise CatalogError(f"Unknown acceptance criteria: {missing_text}")
        return selected


def _load_string_list(raw_value: object, field_name: str, *, default: list[str] | None = None) -> list[str]:
    if raw_value is None:
        if default is None:
            raise CatalogError(f"Catalog requires a non-empty '{field_name}' list")
        return default

    if not isinstance(raw_value, list) or not raw_value or not all(isinstance(item, str) and item for item in raw_value):
        raise CatalogError(f"Catalog requires a non-empty '{field_name}' list")
    return list(raw_value)


def load_catalog(path: str | Path) -> CriteriaCatalog:
    catalog_path = Path(path).resolve()
    with catalog_path.open("r", encoding="utf-8") as handle:
        raw_catalog = yaml.safe_load(handle) or {}

    if not isinstance(raw_catalog, dict):
        raise CatalogError("Catalog root must be a mapping")

    project_root_raw = raw_catalog.get("project_root", ".")
    if not isinstance(project_root_raw, str) or not project_root_raw:
        raise CatalogError("'project_root' must be a non-empty string")
    project_root = (catalog_path.parent / project_root_raw).resolve()

    source_paths = _load_string_list(raw_catalog.get("source_paths"), "source_paths")
    test_paths = _load_string_list(raw_catalog.get("test_paths"), "test_paths", default=["tests"])

    raw_criteria = raw_catalog.get("acceptance_criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise CatalogError("Catalog requires a non-empty 'acceptance_criteria' list")

    seen_ids: set[str] = set()
    acceptance_criteria: list[CriterionDefinition] = []
    for raw_criterion in raw_criteria:
        if not isinstance(raw_criterion, dict):
            raise CatalogError("Each acceptance criterion must be an object")

        criterion_id = raw_criterion.get("id")
        title = raw_criterion.get("title")
        description = raw_criterion.get("description")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise CatalogError("Each acceptance criterion requires a non-empty 'id'")
        if criterion_id in seen_ids:
            raise CatalogError(f"Duplicate acceptance criterion id: {criterion_id}")
        if not isinstance(title, str) or not title:
            raise CatalogError(f"{criterion_id}: missing title")
        if not isinstance(description, str) or not description:
            raise CatalogError(f"{criterion_id}: missing description")

        seen_ids.add(criterion_id)
        acceptance_criteria.append(
            CriterionDefinition(
                id=criterion_id,
                title=title,
                description=description,
            )
        )

    return CriteriaCatalog(
        catalog_path=catalog_path,
        project_root=project_root,
        source_paths=source_paths,
        test_paths=test_paths,
        acceptance_criteria=acceptance_criteria,
    )
