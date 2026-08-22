# RiftKeep Backup / Retention Policy

This policy is authoritative for RiftKeep milestone packaging and full `/mnt` recovery backups.

## Milestone retention

Keep **only the latest two certified final milestone ZIPs** in `/mnt/data`.

At the current checkpoint the retained releases are:

- `RiftKeepRules_Engine_Milestone18.zip`
- `RiftKeepRules_Engine_Milestone19.zip`

When M19 is certified, rotate to M18 + M19 and delete M17. Continue the same latest-two rule for any future maintenance milestone.

## Never retain as release backups

Delete after the milestone release gate finishes:

- `*_candidate.zip`
- stage directories
- smoke/extraction directories
- duplicate milestone uploads/copies
- audit-only milestone copies once their changes are merged into the certified release
- milestones older than the latest two certified releases

## Full `/mnt` backup inclusion policy

A new full recovery backup must **not recursively capture historical release archives**.
Before creating it:

1. Rotate `/mnt/data` to the latest two certified final milestone ZIPs.
2. Remove stale candidate/stage/smoke artifacts.
3. Exclude all prior `RiftKeep_FULL_MNT_Backup_*.tar*` files and their sidecars from the new archive.
4. Include the active project/recovery tree, authoritative source inputs, current metadata/bootstraps, and only the latest two certified final milestone ZIPs.
5. Create the archive outside `/mnt`, then move the verified archive into `/mnt/data` so it cannot include itself.
6. Record SHA-256 and run archive-integrity + restore checks.

## Bootstrap retention

Keep bootstraps/restore metadata needed for the latest two certified milestones. Older bootstrap artifacts may be removed after the newer two recovery points are independently restore-tested.

## Safety rule

Do not delete authoritative source inputs (Core/Tournament PDFs, card corpus, official-source snapshots) merely because they are older than two milestones. The two-release rule applies to **packaged milestone backups**, not source/version history inside the engine.
