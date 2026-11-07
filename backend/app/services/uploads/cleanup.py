"""Orphaned-object sweep.

Object storage and the database cannot share one transaction. Uploads write the object first and the row second, and on
a failed commit the writer deletes its own objects (see storage.delete_quietly). If that compensating delete also
fails, or the process dies between the two writes, an object can be left that no row references. This sweep finds such
objects under the prefixes RouteProof owns and removes them once they are older than a grace period, so in-flight
uploads (object written, row not yet committed) are never touched.

    python -m app.services.uploads.cleanup             # dry run: report only
    python -m app.services.uploads.cleanup --delete    # actually remove orphans
"""
import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BillingExport, Pod
from app.services.uploads.storage import Storage, get_storage

log = logging.getLogger("routeproof.cleanup")

MANAGED_PREFIXES = ("pods/", "exports/")


def referenced_keys(db: Session) -> set[str]:
    keys: set[str] = set()
    for orig, up in db.execute(select(Pod.original_image_path, Pod.uploaded_image_path)):
        keys.update(k for k in (orig, up) if k)
    keys.update(k for k in db.scalars(select(BillingExport.file_path)) if k)
    return keys


def find_orphans(db: Session, st: Storage | None = None, *, grace_hours: int | None = None,
                 now: datetime | None = None) -> list[str]:
    st = st or get_storage()
    grace = timedelta(hours=get_settings().orphan_grace_hours if grace_hours is None else grace_hours)
    cutoff = (now or datetime.now(timezone.utc)) - grace
    refs = referenced_keys(db)
    out = []
    for prefix in MANAGED_PREFIXES:
        for key, modified in st.list(prefix):
            if key not in refs and modified < cutoff:
                out.append(key)
    return out


def sweep_orphans(db: Session, st: Storage | None = None, *, delete: bool = False, grace_hours: int | None = None,
                  now: datetime | None = None) -> dict:
    st = st or get_storage()
    orphans = find_orphans(db, st, grace_hours=grace_hours, now=now)
    removed, failed = [], []
    if delete:
        for k in orphans:
            try:
                st.delete(k)
                removed.append(k)
            except Exception:
                failed.append(k)
                log.exception("storage.orphan_delete_failed", extra={"storage_key": k})
    log.info("storage.orphan_sweep", extra={"orphans": len(orphans), "removed": len(removed), "failed": len(failed), "dry_run": not delete})
    return {"orphans": orphans, "removed": removed, "failed": failed, "dry_run": not delete}


def main() -> None:
    from app.core.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--delete", action="store_true", help="remove orphans (default is a dry run)")
    ap.add_argument("--grace-hours", type=int, default=None, help="only objects older than this (default ORPHAN_GRACE_HOURS)")
    a = ap.parse_args()
    with SessionLocal() as db:
        r = sweep_orphans(db, delete=a.delete, grace_hours=a.grace_hours)
    for k in r["orphans"]:
        print(("removed " if k in r["removed"] else "orphan  ") + k)
    print(f"{len(r['orphans'])} orphan(s); {len(r['removed'])} removed; {len(r['failed'])} failed; dry_run={r['dry_run']}")


if __name__ == "__main__":
    main()
