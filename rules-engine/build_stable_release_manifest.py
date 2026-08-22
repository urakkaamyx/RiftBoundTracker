#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from riftkeep_rules.release_identity import write_stable_release_manifest, validate_stable_release_manifest
manifest=write_stable_release_manifest(ROOT)
result=validate_stable_release_manifest(ROOT)
print(json.dumps({'written':'data/canonical/stable_release_manifest.json','artifactCount':len(manifest['artifactHashes']),'validation':result},indent=2))
raise SystemExit(0 if result.get('passed') else 1)
