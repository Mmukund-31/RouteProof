import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_billing
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.ratelimit import limit
from app.models import ClientViewLink, User
from app.schemas.requests import ClientLinkIn
from app.schemas.serializers import page
from app.services import client_links as svc
from app.services.uploads.storage import get_storage

# Staff side: create, list and revoke links (billing executives only).
router = APIRouter(prefix="/client-links", tags=["client-links"])
# Public, read-only side: the link token is the only credential and it scopes everything.
public = APIRouter(prefix="/client-view", tags=["client-view"])


@router.post("", status_code=201)
def create(body: ClientLinkIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    link, token = svc.create_link(db, user.id, client_id=body.client_id, trip_ids=body.trip_ids, billing_cycle=body.billing_cycle,
                                  expires_in_days=body.expires_in_days, label=body.label)
    out = svc.link_out(link)
    out["url"] = f"{get_settings().public_app_url.rstrip('/')}/view/{token}"  # shown once; only the hash is stored
    return out


@router.get("")
def list_links(client_id: uuid.UUID | None = None, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100),
               user: User = Depends(require_billing), db: Session = Depends(get_db)):
    q = select(ClientViewLink)
    if client_id:
        q = q.where(ClientViewLink.client_id == client_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(ClientViewLink.created_at.desc()).limit(page_size).offset((page_no - 1) * page_size)).unique()
    return page([svc.link_out(r) for r in rows], total, page_no, page_size)


@router.post("/{link_id}/revoke")
def revoke(link_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    link = db.get(ClientViewLink, link_id)
    if not link:
        raise NotFound("Link")
    return svc.link_out(svc.revoke_link(db, user.id, link))


@public.get("/{token}", dependencies=[Depends(limit("client_view", 60))])
def view(token: str, response: Response, db: Session = Depends(get_db)):
    link = svc.resolve(db, token)
    trips = svc.scoped_trips(db, link)
    svc.record_access(db, link, "opened")
    response.headers["Cache-Control"] = "private, no-store"
    return svc.view_payload(link, trips)


@public.get("/{token}/trips/{trip_id}/pod-image", dependencies=[Depends(limit("client_view_image", 120))])
def pod_image(token: str, trip_id: uuid.UUID, db: Session = Depends(get_db)):
    link = svc.resolve(db, token)
    trip = next((t for t in svc.scoped_trips(db, link) if t.id == trip_id), None)
    pod = svc.verified_pod(trip) if trip else None
    if not pod:  # outside the link's scope and "no verified POD yet" look the same: nothing to see
        raise NotFound("POD image")
    try:
        data = get_storage().get(pod.uploaded_image_path)
    except Exception:
        raise NotFound("POD image")
    svc.record_access(db, link, "image_viewed", trip)
    ext = pod.uploaded_image_path.rsplit(".", 1)[-1].replace("jpg", "jpeg")
    return Response(data, media_type=f"image/{ext}", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                                                             "Content-Disposition": f'inline; filename="{trip.trip_reference}-POD.{ext}"'})

