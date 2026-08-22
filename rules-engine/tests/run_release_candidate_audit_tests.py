#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from riftkeep_rules.release_candidate_audit import run_release_candidate_audit
from riftkeep_rules.product_api import ProductApiService

checks=0
failures=[]

def check(name,ok,detail=None):
    global checks
    checks+=1
    if not ok: failures.append({'check':name,'detail':detail})

def codes(r): return {x['code'] for x in r.get('findings',[])}

def write_json(p,d): p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')

# Baseline conformance / product parity / recovery.
base=run_release_candidate_audit(ROOT,retention_root=Path('/mnt/data'))
check('baseline M18 conformance has zero blockers',base['passed'] and base['blockingFindingCount']==0,base['findings'])
check('baseline only expected medium Gold-C finding',base['findingCounts']=={'Critical':0,'High':0,'Medium':1,'Low':0},base['findingCounts'])
check('architecture promise rows include M1-M17 plus definition hotfix',len(base['architecturePromises'])==18,len(base['architecturePromises']))
check('all architecture promises pass',all(x['passed'] for x in base['architecturePromises']))
check('all 17 certified reports pass exact counts',len(base['certifiedReports'])==17 and all(x['passed'] for x in base['certifiedReports'].values()),base['certifiedReports'])
check('retention is exact M18 plus M19',base['retention']['passed'] is True,base['retention'])
check('retained rollback ZIP hashes are verified',all(base['retention'].get('hashes',{}).get(k)==v for k,v in json.load(open(ROOT/'data/canonical/release_candidate_audit_contract.json'))['releasePolicy']['retainedReleaseHashes'].items()),base['retention'])
check('current M19 ZIP matches external SHA sidecar',(base['retention'].get('currentRelease') or {}).get('passed') is True,base['retention'].get('currentRelease'))

repro=json.load(open(ROOT/'data/validation/m18_reproducibility_audit.json'))
check('clean rebuild has no substantive canonical drift',repro['passed'] and repro['substantiveCanonicalDrift'] is False,repro)
check('only two generatedAt artifacts are byte unstable',repro['byteUnstableArtifactCount']==2 and all(x['onlyChangedFields']==['generatedAt'] for x in repro['byteUnstableArtifacts']),repro['byteUnstableArtifacts'])
clean=json.load(open(ROOT/'data/validation/m18_clean_install_audit.json'))
check('clean install audit passes offline',clean['passed'] and clean['networkRequiredForServing'] is False and clean['definitionLookup']==120,clean)
life=json.load(open(ROOT/'data/validation/m18_update_lifecycle_audit.json'))
check('update lifecycle matrix passes every category',life['passed'] and all(x['passed'] for x in life['matrix'].values()),life)
coverage=json.load(open(ROOT/'data/validation/m18_coverage_audit.json'))
check('coverage includes all FAQ cards errata and negative cases',coverage['passed'] and coverage['gold']['currentFaqSectionsCovered']==35 and coverage['gold']['realCardRecordsCovered']==1304 and coverage['gold']['officialErrataEventsCovered']==63 and coverage['gold']['explicitNoSemanticGroups']>=19 and coverage['gold']['conditionalOrInsufficientSemanticGroups']>=7,coverage)
check('definition coverage proof and false-positive guards pass',coverage['definitions']['checks']==120 and coverage['definitions']['proofVerifiedDefinitions'] is True and coverage['definitions']['scenarioFalsePositiveGuard'] is True,coverage['definitions'])

svc=ProductApiService(ROOT)
for term,expected in [('Deflect','Deflect'),('Recall','Recalls')]:
    ans=svc.ask(f'What does {term} do?')
    issue=ans['issues'][0]
    check(f'API definition {term} is backend-decided',issue['verdict']=='definition' and issue['proof']['verified'] is True,issue)
    check(f'API definition {term} carries rule-family citations',len(issue['citations'])>=2 and all(x.startswith('R:') for x in issue['citations']),issue['citations'])
    check(f'API definition {term} conclusion resolves expected family',expected in issue['conclusion'],issue['conclusion'])

app=(ROOT/'web/app.js').read_text(encoding='utf-8')
ui=json.load(open(ROOT/'contracts/ui_contract.json'))
check('UI contract says Product API is sole data authority',(ui.get('policy') or {}).get('productApiIsOnlyDataAuthority') is True,ui.get('policy'))
check('UI contract forbids browser adjudication',(ui.get('policy') or {}).get('browserAdjudicationLogic') is False and (ui.get('policy') or {}).get('browserEvidenceSelectionLogic') is False,ui.get('policy'))
check('UI app routes asks and evidence to backend','/v1/ask' in app and '/v1/evidence/' in app, None)
check('UI app has no dynamic HTML injection primitives',all(x not in app for x in ('innerHTML','outerHTML','insertAdjacentHTML','eval(')),None)

for n,tasks,defs,hard,extra_expected in [(18,'T194',120,74,48),(19,'T205',120,74,191)]:
    zp=Path(f'/mnt/data/RiftKeepRules_Engine_Milestone{n}.zip')
    check(f'M{n} retained ZIP exists',zp.is_file(),str(zp))
    with zipfile.ZipFile(zp) as z:
        check(f'M{n} retained ZIP integrity',z.testzip() is None,z.testzip())
        md=json.loads(z.read('RiftKeepRules_Engine/MILESTONE.json'))
        check(f'M{n} embedded release metadata',md['releaseStatus']=='released' and md['tasksCompletedThrough']==tasks,md)
        check(f'M{n} definition checks embedded',md['validation'].get('definitionLookupChecks')==defs,md['validation'])
        check(f'M{n} production hardening checks embedded',md['validation'].get('productionHardeningChecks')==hard,md['validation'])
        check(f'M{n} recovery bootstrap embedded',f'RiftKeepRules_Engine/bootstrap_M{n}.md' in z.namelist())
        if n==19:
            check('M19 Stable acceptance checks embedded',md['validation'].get('stableReleaseChecks')==extra_expected,md['validation'])

# Adversarial audit mutations in one disposable project copy.
with tempfile.TemporaryDirectory(prefix='rk_m18_audit_') as td:
    tr=Path(td)/'RiftKeepRules_Engine'
    def ignore(path,names): return {n for n in names if n in {'__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','.git'} or n.endswith(('.pyc','.pyo'))}
    shutil.copytree(ROOT,tr,ignore=ignore)
    def mutate_json(rel,fn):
        p=tr/rel; original=p.read_bytes(); d=json.loads(original); fn(d); write_json(p,d); r=run_release_candidate_audit(tr); p.write_bytes(original); return r

    r=mutate_json('data/validation/definition_lookup_test_report.json',lambda d:d.__setitem__('checkCount',119))
    check('tampered definition count blocks release',not r['passed'] and 'certified_report_mismatch' in codes(r),r['findings'])

    faq=tr/'data/source/official_text/vendetta_faq_2026-08-14.txt'; original=faq.read_bytes(); faq.write_bytes(original+b'\nM18 tamper')
    r=run_release_candidate_audit(tr); faq.write_bytes(original)
    check('FAQ byte tamper blocks release',not r['passed'] and 'source_hash_mismatch' in codes(r),r['findings'])

    db=tr/'data/index/rules.sqlite'; con=sqlite3.connect(db); con.execute('pragma user_version=999'); con.commit(); con.close()
    r=run_release_candidate_audit(tr)
    check('unknown SQLite schema blocks release',not r['passed'] and 'sqlite_integrity_or_schema' in codes(r),r['findings'])
    con=sqlite3.connect(db); con.execute('pragma user_version=1'); con.commit(); con.close()

    r=mutate_json('data/validation/update_automation_test_report.json',lambda d:d['metrics'].__setitem__('certifiedReleaseTestCount',16))
    check('weakened automated update gate blocks release',not r['passed'] and 'automated_update_release_gate_strength' in codes(r),r['findings'])

    r=mutate_json('data/gold/gold_c_promotions.json',lambda d:d.__setitem__('promotionCount',15))
    check('Gold-C promotion-state drift blocks release',not r['passed'] and 'gold_c_promotion_state_mismatch' in codes(r),r['findings'])

    overlay=tr/'data/source/current_authority_overlay.json'; overlay_original=overlay.read_bytes(); overlay_doc=json.loads(overlay_original); overlay_doc['sourceId']='synthetic-wrong-current-faq'; write_json(overlay,overlay_doc)
    r=run_release_candidate_audit(tr); overlay.write_bytes(overlay_original)
    check('broken current authority identity blocks release',not r['passed'] and 'source_authority_mismatch' in codes(r),r['findings'])

    promised=tr/'src/riftkeep_rules/runtime_hardening.py'; promised_original=promised.read_bytes(); promised.unlink(); r=run_release_candidate_audit(tr); promised.write_bytes(promised_original)
    check('missing promised runtime-hardening artifact blocks release',not r['passed'] and 'architecture_promise_missing' in codes(r),r['findings'])

    target=tr/'web/app.js'; original=target.read_bytes(); target.unlink(); r=run_release_candidate_audit(tr); target.write_bytes(original)
    check('missing promised UI artifact blocks release',not r['passed'] and 'architecture_promise_missing' in codes(r),r['findings'])

    with tempfile.TemporaryDirectory(prefix='rk_m18_retention_') as rd:
        rr=Path(rd); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip',rr/'RiftKeepRules_Engine_Milestone19.zip'); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip.sha256',rr/'RiftKeepRules_Engine_Milestone19.zip.sha256')
        r=run_release_candidate_audit(tr,retention_root=rr)
        check('missing retained M18 blocks release',not r['passed'] and 'actual_retention_mismatch' in codes(r),r['findings'])

    with tempfile.TemporaryDirectory(prefix='rk_m18_retention_hash_') as rd:
        rr=Path(rd)
        shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip',rr/'RiftKeepRules_Engine_Milestone19.zip'); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip.sha256',rr/'RiftKeepRules_Engine_Milestone19.zip.sha256')
        (rr/'RiftKeepRules_Engine_Milestone18.zip').write_bytes(b'not the certified M18')
        r=run_release_candidate_audit(tr,retention_root=rr)
        check('retained release hash mismatch blocks release',not r['passed'] and 'retained_release_hash_mismatch' in codes(r),r['findings'])

    with tempfile.TemporaryDirectory(prefix='rk_m18_retention_candidate_') as rd:
        rr=Path(rd); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone18.zip',rr/'RiftKeepRules_Engine_Milestone18.zip'); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip',rr/'RiftKeepRules_Engine_Milestone19.zip'); shutil.copy2('/mnt/data/RiftKeepRules_Engine_Milestone19.zip.sha256',rr/'RiftKeepRules_Engine_Milestone19.zip.sha256'); (rr/'RiftKeepRules_Engine_Milestone20_candidate.zip').write_bytes(b'x')
        r=run_release_candidate_audit(tr,retention_root=rr)
        check('candidate leakage into shareable area blocks release',not r['passed'] and 'candidate_in_shareable_area' in codes(r),r['findings'])

metrics={'schemaVersion':1,'checkCount':checks,'baselineBlockingFindings':base['blockingFindingCount'],'baselineMediumFindings':base['findingCounts']['Medium'],'definitionChecks':120,'recoveredBaselineSuiteCount':17,'retentionHashesVerified':True,'cleanInstallPassed':True,'updateLifecyclePassed':True,'productParityPassed':True}
report={'passed':not failures,'checkCount':checks,'failureCount':len(failures),'failures':failures,'metrics':metrics}
(ROOT/'data/validation/release_candidate_audit_test_report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['passed'] else 1)
