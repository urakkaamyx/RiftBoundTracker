# RiftKeep Milestone Backup Policy

Effective with Milestone 8, a milestone is **not considered fully closed for recovery purposes** until its recovery backup is created and restore-tested.

For every completed milestone `M#`:

1. Finish the milestone implementation and freeze its scope in `ROADMAP.md` / `TASKS.md`.
2. Build the canonical milestone release artifact and test that exact artifact from a clean extraction.
3. Create `bootstrap_M#.md` containing the exact certified release artifact, hashes, validation baseline, source/version authority state, known warnings, current/next task boundary, and step-by-step restore/resume procedure.
4. Capture a **full `/mnt` filesystem backup**, not merely the active project or `/mnt/data` subproject. The archive must be created outside `/mnt` first so it cannot recursively include itself.
5. Generate a SHA-256 sidecar for the completed full backup.
6. Open/list/test the completed backup and verify that `bootstrap_M#.md`, the certified milestone release artifact, and the active project/recovery trees are present.
7. Record the backup filename/hash in milestone backup metadata.
8. Only after the backup passes may development proceed to the next milestone.

## State distinction rule

A backup may contain work started after the certified milestone. The bootstrap must always distinguish:

- **Certified milestone state** — exact release artifact that passed its milestone gate.
- **Post-milestone development state** — any newer worktree; never assume it reproduces the prior milestone baseline.

Recovery must begin from the certified artifact unless the bootstrap explicitly states that the post-milestone tree has itself passed a newer release gate.

## Naming

- Bootstrap: `bootstrap_M#.md`
- Full backup: `RiftKeep_FULL_MNT_Backup_M#.tar.zst`
- Hash sidecar: `RiftKeep_FULL_MNT_Backup_M#.tar.zst.sha256`
- Backup metadata directory: `/mnt/data/RiftKeep_Milestone_Backups/M#/`
