from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .authority import load_authority_status


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    blocking: bool
    detail: Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _add(items:list[Finding], code:str, severity:str, detail:Any, blocking:bool|None=None) -> None:
    items.append(Finding(code,severity,severity in {'Critical','High'} if blocking is None else bool(blocking),detail))


def _count(report:dict[str,Any]) -> int|None:
    if isinstance(report.get('checkCount'),int): return report['checkCount']
    if isinstance(report.get('caseCount'),int): return report['caseCount']
    return None


def run_release_candidate_audit(root:Path, *, retention_root:Path|None=None) -> dict[str,Any]:
    root=Path(root).resolve()
    contract=_load(root/'data/canonical/release_candidate_audit_contract.json')
    findings:list[Finding]=[]

    # M1-M17 + Definition hotfix promise matrix.
    promise=[]
    for m in contract['milestones']:
        missing_art=[x for x in m['requiredArtifacts'] if not (root/x).is_file()]
        missing_reports=[]; failed_reports=[]
        for name in m['requiredReports']:
            p=root/'data/validation'/name
            if not p.is_file(): missing_reports.append(name); continue
            if not _load(p).get('passed'): failed_reports.append(name)
        passed=not (missing_art or missing_reports or failed_reports)
        row={'milestone':m['milestone'],'name':m['name'],'passed':passed,'missingArtifacts':missing_art,'missingReports':missing_reports,'failedReports':failed_reports}
        promise.append(row)
        if not passed: _add(findings,'architecture_promise_missing','Critical',row)

    # Certified report counts.
    report_rows={}
    for name,expected in contract['expectedReports'].items():
        p=root/'data/validation'/name
        if not p.is_file():
            report_rows[name]={'passed':False,'expected':expected,'actual':None}; _add(findings,'certified_report_missing','Critical',name); continue
        d=_load(p); actual=_count(d); ok=bool(d.get('passed')) and actual==expected
        report_rows[name]={'passed':ok,'expected':expected,'actual':actual}
        if not ok: _add(findings,'certified_report_mismatch','Critical',{'report':name,'expected':expected,'actual':actual,'reportedPassed':d.get('passed')})

    # Current authority/provenance.
    a=contract['sourceAuthority']
    core=_load(root/'data/canonical/core_rules.json'); tour=_load(root/'data/canonical/tournament_rules.json'); cards=_load(root/'data/canonical/cards.json')
    overlay=_load(root/'data/source/current_authority_overlay.json'); ch=_load(root/'data/source/rule_versions/core/history.json'); th=_load(root/'data/source/rule_versions/tournament/history.json')
    err=_load(root/'data/canonical/official_errata_history.json')
    authority_checks={
      'coreRuleCount':(len(core['rules']),a['coreRuleCount']),
      'tournamentRuleCount':(len(tour['rules']),a['tournamentRuleCount']),
      'cardCount':(len(cards['cards']),a['cardCount']),
      'faqSectionCount':(overlay.get('localSnapshot',{}).get('sectionCount'),a['faqSectionCount']),
      'errataEventCount':(err.get('errataEventCount'),a['errataEventCount']),
      'errataAffectedPrintings':(err.get('effectiveCardPrintingCount'),a['errataAffectedPrintings']),
      'coreSourceId':(ch.get('currentSourceId'),a['currentCoreSourceId']),
      'tournamentSourceId':(th.get('currentSourceId'),a['currentTournamentSourceId']),
      'faqSourceId':(overlay.get('sourceId'),a['currentFaqSourceId']),
      'cardSourceSha256':(cards.get('metadata',{}).get('sourceSha256'),a['cardSourceSha256']),
    }
    for field,(actual,expected) in authority_checks.items():
        if actual!=expected: _add(findings,'source_authority_mismatch','Critical',{'field':field,'expected':expected,'actual':actual})
    source_hashes={
      'coreSourceSha256':_sha(root/'data/source/core_rules.pdf'),
      'tournamentSourceSha256':_sha(root/'data/source/tournament_rules.pdf'),
      'faqSnapshotSha256':_sha(root/'data/source/official_text/vendetta_faq_2026-08-14.txt'),
    }
    for field,actual in source_hashes.items():
        if actual!=a[field]: _add(findings,'source_hash_mismatch','Critical',{'field':field,'expected':a[field],'actual':actual})
    for family,hist in [('core',ch),('tournament',th)]:
        cur=next((v for v in hist.get('versions',[]) if v.get('sourceId')==hist.get('currentSourceId')),None)
        if not cur: _add(findings,'current_version_record_missing','Critical',family); continue
        path=root/cur['sourceFile']
        if not path.is_file() or _sha(path)!=cur.get('sourceSha256'):
            _add(findings,'version_ledger_hash_mismatch','Critical',{'family':family,'sourceId':cur.get('sourceId')})
    if overlay.get('localSnapshot',{}).get('sha256')!=source_hashes['faqSnapshotSha256']:
        _add(findings,'faq_overlay_hash_mismatch','Critical',{'overlay':overlay.get('localSnapshot',{}).get('sha256'),'actual':source_hashes['faqSnapshotSha256']})

    # Stable IDs and SQLite migration/integrity.
    for family,data in [('core',core),('tournament',tour)]:
        ids=[r.get('internalRuleId') for r in data['rules']]
        if None in ids or len(ids)!=len(set(ids)):
            _add(findings,'stable_rule_id_failure','Critical',{'family':family,'count':len(ids),'unique':len(set(ids))})
    try:
        db=root/'data/index/rules.sqlite'; con=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)
        quick=str(con.execute('PRAGMA quick_check').fetchone()[0]); uv=int(con.execute('PRAGMA user_version').fetchone()[0]); con.close()
        if quick!='ok' or uv!=contract['releasePolicy']['requiredIndexSchemaVersion']:
            _add(findings,'sqlite_integrity_or_schema','Critical',{'quickCheck':quick,'userVersion':uv})
    except Exception as exc:
        _add(findings,'sqlite_open_failed','Critical',f'{type(exc).__name__}: {exc}')

    # Gold / adjudication coverage and Definition Lookup hotfix.
    gm=_load(root/'data/gold/gold_manifest.json'); gc=_load(root/'data/gold/gold_corpus.json'); gp=_load(root/'data/gold/gold_c_promotions.json')
    policy=contract['releasePolicy']
    if len(gc.get('cases',[]))!=gm.get('expectedCounts',{}).get('total'):
        _add(findings,'gold_case_count_mismatch','Critical',{'manifest':gm.get('expectedCounts',{}).get('total'),'actual':len(gc.get('cases',[]))})
    if gp.get('goldCFixtureCount')!=policy['goldCFixtureCount'] or gp.get('promotionCount')!=policy['goldCPromoted'] or gp.get('remainingReportOnlyCount')!=policy['goldCRemainingReportOnly']:
        _add(findings,'gold_c_promotion_state_mismatch','High',{'expected':{'fixtures':policy['goldCFixtureCount'],'promoted':policy['goldCPromoted'],'remaining':policy['goldCRemainingReportOnly']},'actual':{'fixtures':gp.get('goldCFixtureCount'),'promoted':gp.get('promotionCount'),'remaining':gp.get('remainingReportOnlyCount')}})
    if policy['goldCRemainingReportOnly']:
        _add(findings,'gold_c_report_only_remaining','Medium',{'remaining':policy['goldCRemainingReportOnly']},blocking=False)
    definitions=_load(root/'data/validation/definition_lookup_test_report.json')
    dm=definitions.get('metrics') or {}
    if not (definitions.get('passed') and definitions.get('checkCount')==120 and dm.get('proofVerifiedDefinitions') and dm.get('scenarioFalsePositiveGuard')):
        _add(findings,'definition_lookup_release_guarantee','High',{'passed':definitions.get('passed'),'checkCount':definitions.get('checkCount'),'metrics':dm})

    # Aggregate-independent release state.  The M18 suite must not consume
    # validation_summary/project_audit because those outer gates consume this suite.
    # Current authority is checked directly from source state instead.
    authority=load_authority_status(root)
    auto=_load(root/'data/validation/update_automation_test_report.json')
    if not authority.get('currentRulesComplete'):
        _add(findings,'current_authority_incomplete','Critical',authority)
    if (auto.get('metrics') or {}).get('certifiedReleaseTestCount')!=policy['requiredCertifiedReleaseSuiteCount']:
        _add(findings,'automated_update_release_gate_strength','Critical',{'expected':policy['requiredCertifiedReleaseSuiteCount'],'actual':(auto.get('metrics') or {}).get('certifiedReleaseTestCount')})

    # Recovery/retention declaration and actual shareable area.
    backup_policy=(root/'BACKUP_POLICY.md').read_text(encoding='utf-8')
    expected_names=[f'RiftKeepRules_Engine_Milestone{n}.zip' for n in policy['latestTwoMilestones']]
    if not all(n in backup_policy for n in expected_names):
        _add(findings,'backup_policy_retention_drift','Medium',{'expected':expected_names},blocking=False)
    retention={'expected':expected_names,'actual':None,'candidates':[],'passed':None}
    if retention_root is not None:
        rr=Path(retention_root)
        actual=sorted(p.name for p in rr.glob('RiftKeepRules_Engine_Milestone*.zip') if 'candidate' not in p.name.lower())
        candidates=sorted(p.name for p in rr.glob('*candidate*'))
        retention.update(actual=actual,candidates=candidates,passed=(actual==expected_names and not candidates))
        if actual!=expected_names: _add(findings,'actual_retention_mismatch','High',retention)
        if candidates: _add(findings,'candidate_in_shareable_area','High',candidates)
        expected_hashes=policy.get('retainedReleaseHashes') or {}
        actual_hashes={}
        for name,expected_hash in expected_hashes.items():
            f=rr/name
            actual_hashes[name]=_sha(f) if f.is_file() else None
            if actual_hashes[name]!=expected_hash:
                _add(findings,'retained_release_hash_mismatch','High',{'file':name,'expected':expected_hash,'actual':actual_hashes[name]})
        retention['hashes']=actual_hashes
        current_archive=policy.get('currentReleaseArchive')
        current_sidecar=policy.get('currentReleaseHashSidecar')
        if current_archive and current_sidecar:
            archive_path=rr/current_archive; sidecar_path=rr/current_sidecar
            sidecar_hash=None; actual_current_hash=_sha(archive_path) if archive_path.is_file() else None
            if sidecar_path.is_file():
                parts=sidecar_path.read_text(encoding='utf-8').strip().split()
                sidecar_hash=parts[0] if parts else None
            retention['currentRelease']={'archive':current_archive,'sidecar':current_sidecar,'actualSha256':actual_current_hash,'sidecarSha256':sidecar_hash,'passed':bool(actual_current_hash and sidecar_hash and actual_current_hash==sidecar_hash)}
            if not archive_path.is_file() or not sidecar_path.is_file():
                _add(findings,'current_release_sidecar_missing','High',retention['currentRelease'])
            elif actual_current_hash!=sidecar_hash:
                _add(findings,'current_release_sidecar_hash_mismatch','High',retention['currentRelease'])

    sev={k:0 for k in ['Critical','High','Medium','Low']}
    for f in findings: sev[f.severity]=sev.get(f.severity,0)+1
    blocking=[f for f in findings if f.blocking]
    result={
      'schemaVersion':1,'passed':not blocking,'releaseCandidateReady':not blocking,'blockingFindingCount':len(blocking),'findingCounts':sev,
      'architecturePromises':promise,'certifiedReports':report_rows,
      'authorityChecks':{k:{'actual':x,'expected':y,'passed':x==y} for k,(x,y) in authority_checks.items()},
      'sourceHashes':{k:{'actual':v,'expected':a[k],'passed':v==a[k]} for k,v in source_hashes.items()},
      'retention':retention,'findings':[asdict(f) for f in findings]
    }
    (root/'data/validation/release_candidate_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
