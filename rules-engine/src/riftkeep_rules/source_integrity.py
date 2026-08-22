from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .official_sources import validate_snapshot_content


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_current_overlays(root: Path) -> dict[str, Any]:
    manifest_path = root / 'data/source/official_source_manifest.json'
    catalog_path = root / 'data/source/official_ruling_catalog.json'
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    if not manifest_path.exists():
        return {'passed': False, 'errors': ['missing_manifest'], 'checks': [], 'sources': []}
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    catalog = {}
    if catalog_path.exists():
        catalog = (json.loads(catalog_path.read_text(encoding='utf-8')) or {}).get('sections') or {}

    active = [s for s in manifest.get('sources', []) if s.get('status') == 'current_overlay']
    if not active:
        errors.append('no_current_overlay_declared')

    for meta in active:
        sid = str(meta.get('id') or '')
        report: dict[str, Any] = {'sourceId': sid, 'passed': True, 'errors': [], 'checks': {}}
        latest_path = root / 'data/source/snapshots' / sid / 'latest.json'
        report['checks']['latestPointerExists'] = latest_path.exists()
        if not latest_path.exists():
            report['errors'].append('missing_latest_pointer')
            report['passed'] = False
            sources.append(report)
            errors.append(f'{sid}:missing_latest_pointer')
            continue

        try:
            ptr = json.loads(latest_path.read_text(encoding='utf-8'))
        except Exception as exc:
            report['errors'].append(f'invalid_latest_pointer:{type(exc).__name__}')
            report['passed'] = False
            sources.append(report)
            errors.append(f'{sid}:invalid_latest_pointer')
            continue

        record_path = root / str(ptr.get('snapshotRecord') or '')
        archive_path = root / str(ptr.get('archivePath') or '')
        report['checks']['snapshotRecordExists'] = record_path.exists()
        report['checks']['archiveExists'] = archive_path.exists()
        if not record_path.exists() or not archive_path.exists():
            report['errors'].append('missing_record_or_archive')
            report['passed'] = False
            sources.append(report)
            errors.append(f'{sid}:missing_record_or_archive')
            continue

        snapshot = json.loads(record_path.read_text(encoding='utf-8'))
        expected_sha = str(snapshot.get('sha256') or '')
        actual_sha = _sha256(archive_path)
        report['checks']['archiveHashMatchesSnapshot'] = bool(expected_sha and actual_sha == expected_sha)
        report['checks']['pointerHashMatchesSnapshot'] = str(ptr.get('sha256') or '') == expected_sha
        report['checks']['sourceIdMatches'] = snapshot.get('sourceId') == sid
        report['checks']['sourceUrlMatchesManifest'] = snapshot.get('sourceUrl') == meta.get('url')
        report['checks']['authorityStatusCurrentOverlay'] = (snapshot.get('authority') or {}).get('status') == 'current_overlay'
        precedence = (snapshot.get('authority') or {}).get('precedence') or {}
        report['checks']['precedenceDeclared'] = bool(precedence.get('over')) and precedence.get('onlyWhereDifferent') is True

        validation = validate_snapshot_content(snapshot)
        report['checks']['snapshotValidationPassed'] = bool(validation.get('passed'))
        sections = list(snapshot.get('sections') or [])
        report['checks']['sectionCountMatches'] = int(snapshot.get('sectionCount') or 0) == len(sections)
        profile_min = int((meta.get('validationProfile') or {}).get('minSectionCount') or 0)
        report['checks']['sectionCountMeetsProfile'] = len(sections) >= profile_min
        ids = [str(s.get('evidenceId') or '') for s in sections]
        report['checks']['evidenceIdsUnique'] = len(ids) == len(set(ids)) and all(ids)
        expected_ids = [f'O:{sid}:{i:04d}' for i in range(1, len(sections) + 1)]
        report['checks']['evidenceIdsContiguous'] = ids == expected_ids
        report['checks']['catalogCoversEverySection'] = all(eid in catalog for eid in ids)
        report['checks']['catalogRolesPresent'] = all(bool((catalog.get(eid) or {}).get('role')) and bool((catalog.get(eid) or {}).get('compilerFamily')) for eid in ids)

        failed = [k for k, v in report['checks'].items() if not v]
        if failed:
            report['errors'].extend(failed)
            report['passed'] = False
            errors.extend(f'{sid}:{x}' for x in failed)
        report['sectionCount'] = len(sections)
        report['sha256'] = expected_sha
        report['captureMode'] = snapshot.get('captureMode')
        report['validation'] = validation
        sources.append(report)

    checks.extend({'sourceId': s['sourceId'], 'passed': s['passed']} for s in sources)
    return {
        'schemaVersion': 1,
        'passed': not errors and all(s.get('passed') for s in sources),
        'activeOverlayCount': len(active),
        'errors': errors,
        'checks': checks,
        'sources': sources,
    }
