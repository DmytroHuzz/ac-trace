from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml


class ManifestError(ValueError):
    """Raised when the traceability manifest is invalid."""


@dataclass(frozen=True)
class CodeRef:
    path: str
    symbol: Optional[str] = None
    lines: Optional[str] = None
    mutate: bool = True

    def resolved_path(self, project_root: Path) -> Path:
        return (project_root / self.path).resolve()


@dataclass(frozen=True)
class TestRef:
    path: str
    cases: list[str]

    def resolved_path(self, project_root: Path) -> Path:
        return (project_root / self.path).resolve()


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    title: str
    description: str
    code: list[CodeRef]
    tests: list[TestRef]


@dataclass(frozen=True)
class TraceManifest:
    manifest_path: Path
    project_root: Path
    acceptance_criteria: list[AcceptanceCriterion]

    def find_criteria(
        self, ids: Optional[Iterable[str]] = None
    ) -> list[AcceptanceCriterion]:
        if ids is None:
            return self.acceptance_criteria

        wanted = set(ids)
        selected = [
            criterion
            for criterion in self.acceptance_criteria
            if criterion.id in wanted
        ]
        missing = wanted.difference({criterion.id for criterion in selected})
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ManifestError(f"Unknown acceptance criteria: {missing_text}")
        return selected

    def select(self, ids: Optional[Iterable[str]] = None) -> "TraceManifest":
        return TraceManifest(
            manifest_path=self.manifest_path,
            project_root=self.project_root,
            acceptance_criteria=self.find_criteria(ids),
        )


def _load_code_refs(raw_refs: object, criterion_id: str) -> list[CodeRef]:
    if not isinstance(raw_refs, list) or not raw_refs:
        raise ManifestError(f"{criterion_id}: expected a non-empty 'code' list")

    refs: list[CodeRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            raise ManifestError(f"{criterion_id}: code entry must be an object")
        path = raw_ref.get("path")
        if not isinstance(path, str) or not path:
            raise ManifestError(
                f"{criterion_id}: code entry requires a non-empty 'path'"
            )
        symbol = raw_ref.get("symbol")
        lines = raw_ref.get("lines")
        mutate = raw_ref.get("mutate", True)
        if not isinstance(mutate, bool):
            raise ManifestError(
                f"{criterion_id}: code entry field 'mutate' must be true or false"
            )
        refs.append(
            CodeRef(
                path=path,
                symbol=symbol if isinstance(symbol, str) and symbol else None,
                lines=lines if isinstance(lines, str) and lines else None,
                mutate=mutate,
            )
        )
    return refs


def _load_test_refs(raw_refs: object, criterion_id: str) -> list[TestRef]:
    if not isinstance(raw_refs, list) or not raw_refs:
        raise ManifestError(f"{criterion_id}: expected a non-empty 'tests' list")

    refs: list[TestRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            raise ManifestError(f"{criterion_id}: test entry must be an object")
        path = raw_ref.get("path")
        cases = raw_ref.get("cases")
        if not isinstance(path, str) or not path:
            raise ManifestError(
                f"{criterion_id}: test entry requires a non-empty 'path'"
            )
        if (
            not isinstance(cases, list)
            or not cases
            or not all(isinstance(case, str) and case for case in cases)
        ):
            raise ManifestError(
                f"{criterion_id}: test entry requires a non-empty 'cases' list"
            )
        refs.append(TestRef(path=path, cases=list(cases)))
    return refs


def load_manifest(path: str | Path) -> TraceManifest:
    manifest_path = Path(path).resolve()
    with manifest_path.open("r", encoding="utf-8") as handle:
        raw_manifest = yaml.safe_load(handle) or {}

    if not isinstance(raw_manifest, dict):
        raise ManifestError("Manifest root must be a mapping")

    project_root_raw = raw_manifest.get("project_root", ".")
    if not isinstance(project_root_raw, str) or not project_root_raw:
        raise ManifestError("'project_root' must be a non-empty string")
    project_root = (manifest_path.parent / project_root_raw).resolve()

    raw_criteria = raw_manifest.get("acceptance_criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ManifestError("Manifest requires a non-empty 'acceptance_criteria' list")

    seen_ids: set[str] = set()
    criteria: list[AcceptanceCriterion] = []
    for raw_criterion in raw_criteria:
        if not isinstance(raw_criterion, dict):
            raise ManifestError("Each acceptance criterion must be an object")
        criterion_id = raw_criterion.get("id")
        title = raw_criterion.get("title")
        description = raw_criterion.get("description")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise ManifestError("Each acceptance criterion requires a non-empty 'id'")
        if criterion_id in seen_ids:
            raise ManifestError(f"Duplicate acceptance criterion id: {criterion_id}")
        if not isinstance(title, str) or not title:
            raise ManifestError(f"{criterion_id}: missing title")
        if not isinstance(description, str) or not description:
            raise ManifestError(f"{criterion_id}: missing description")
        seen_ids.add(criterion_id)
        criteria.append(
            AcceptanceCriterion(
                id=criterion_id,
                title=title,
                description=description,
                code=_load_code_refs(raw_criterion.get("code"), criterion_id),
                tests=_load_test_refs(raw_criterion.get("tests"), criterion_id),
            )
        )

    return TraceManifest(
        manifest_path=manifest_path,
        project_root=project_root,
        acceptance_criteria=criteria,
    )


def manifest_to_dict(
    manifest: TraceManifest, *, relative_to: Path | None = None
) -> dict[str, object]:
    base_path = relative_to or manifest.manifest_path.parent

    return {
        "project_root": os.path.relpath(manifest.project_root, base_path),
        "acceptance_criteria": [
            {
                "id": criterion.id,
                "title": criterion.title,
                "description": criterion.description,
                "code": [
                    {
                        key: value
                        for key, value in {
                            "path": code_ref.path,
                            "symbol": code_ref.symbol,
                            "lines": code_ref.lines,
                            "mutate": code_ref.mutate,
                        }.items()
                        if value is not None
                    }
                    for code_ref in criterion.code
                ],
                "tests": [
                    {
                        "path": test_ref.path,
                        "cases": test_ref.cases,
                    }
                    for test_ref in criterion.tests
                ],
            }
            for criterion in manifest.acceptance_criteria
        ],
    }


def dump_manifest(manifest: TraceManifest, *, relative_to: Path | None = None) -> str:
    payload = manifest_to_dict(manifest, relative_to=relative_to)
    return yaml.safe_dump(payload, sort_keys=False)
