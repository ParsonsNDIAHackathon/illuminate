"""Human-confirmed publication of the versioned insight export to NDIA."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from ..config import settings
from . import exports
from .deps import user_id

router = APIRouter(prefix="/api/catalog/ndia", tags=["catalog"])
EVENT_ID = 3
EXPORT_ID = "illuminate-insight-findings"
_state_lock = asyncio.Lock()


class DatasetMetadata(BaseModel):
    """Official event-3 dataset fields exposed by the NDIA catalog."""

    model_config = ConfigDict(extra="forbid")
    event_id: Literal[3] = EVENT_ID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    source_url: HttpUrl
    format: Literal["JSON"]
    size_estimate: str | None = None
    update_frequency: str | None = None
    access_requirements: str | None = None
    license_info: str | None = None
    api_documentation: HttpUrl | None = None
    sample_data_url: HttpUrl | None = None
    schema_description: str | None = None
    quality_notes: str | None = None
    tags: list[str] = Field(min_length=1, max_length=20)


class EventMetadata(BaseModel):
    id: Literal[3] = EVENT_ID
    slug: Literal["ndia-global-defense-hackathon-main-event-washington-dc"]
    title: Literal["NDIA Global Defense Hackathon / Main Event: Washington, DC"]


class ContributionPreview(BaseModel):
    export_id: Literal["illuminate-insight-findings"] = EXPORT_ID
    export_version: str
    export_watermark: str
    event: EventMetadata
    metadata: DatasetMetadata
    confirmation_token: str
    schema_valid: Literal[True] = True
    publication_ready: bool
    credential_configured: bool
    operator_authorization_configured: bool
    contribution_state: str
    remote_dataset_id: str | None = None
    message: str


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True]
    confirmation: Literal["PUBLISH EVENT 3"]
    confirmation_token: str = Field(min_length=20, max_length=512)
    dry_run: bool = False


class ContributionResult(BaseModel):
    export_id: str
    export_version: str
    dataset_id: str | None = None
    contribution_state: str
    message: str
    dry_run: bool
    idempotent: bool = False
    submitted_at: datetime | None = None
    metadata: DatasetMetadata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _state_path() -> Path:
    return settings.data_dir / "ndia-catalog.json"


def _load_state() -> dict[str, Any]:
    try:
        value = json.loads(_state_path().read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True))
    temp.replace(path)


def _truthful_state(state: str | None, dataset_id: str | None) -> str:
    value = state or "not_submitted"
    if value == "published" and not dataset_id:
        return "unknown"
    return value


class PortalError(HTTPException):
    """A sanitized portal error that records whether retry may duplicate."""

    def __init__(self, status_code: int, detail: str, *, uncertain: bool):
        super().__init__(status_code, detail)
        self.uncertain = uncertain


def _public_url(path: str) -> str:
    base = (settings.illuminate_public_url or "https://example.invalid/illuminate").rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _metadata() -> DatasetMetadata:
    return DatasetMetadata(
        name=f"Illuminate Reusable Supply Chain Insight Findings v{exports.VERSION}",
        description=(
            "Versioned, portable supplier-network findings with typed paths, "
            "provenance, truth status, simulation flags, quality, and risk context. "
            f"Export identity: {EXPORT_ID}; schema version: {exports.VERSION}."
        ),
        source_url=_public_url("/api/exports/v1/findings"),
        format="JSON",
        update_frequency="On demand; use export watermark for incremental synchronization",
        access_requirements="Public read-only endpoint; UNCLASSIFIED findings with per-record handling metadata",
        license_info="Mixed / source-specific; see each finding's license and provenance",
        api_documentation=_public_url("/api/exports/v1/fields"),
        sample_data_url=_public_url("/api/exports/v1/sample"),
        schema_description=_public_url("/api/exports/v1/schema"),
        quality_notes="Preserve truth_status, simulated, quality, classification, and provenance fields.",
        tags=["supply-chain", "supplier-risk", "provenance", "interoperability"],
    )


def _review_digest(metadata: DatasetMetadata, watermark: str, user: str) -> str:
    reviewed = {
        "export_id": EXPORT_ID,
        "export_version": exports.VERSION,
        "watermark": watermark,
        "metadata": metadata.model_dump(mode="json"),
        "user": user,
    }
    canonical = json.dumps(reviewed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _confirmation_token(metadata: DatasetMetadata, watermark: str, user: str) -> str:
    payload = json.dumps({
        "digest": _review_digest(metadata, watermark, user),
        "expires": int(_now().timestamp()) + 600,
    }, sort_keys=True, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(
        settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


def _verify_confirmation(token: str, metadata: DatasetMetadata, watermark: str, user: str) -> None:
    try:
        encoded, supplied = token.rsplit(".", 1)
        expected = hmac.new(
            settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(supplied, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload.get("expires", 0) < int(_now().timestamp()):
            raise HTTPException(409, "confirmation expired; review a fresh preview")
        if not hmac.compare_digest(payload.get("digest", ""), _review_digest(metadata, watermark, user)):
            raise ValueError
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(409, "preview changed or was not confirmed; review a fresh preview") from exc


async def _preview(user: str) -> ContributionPreview:
    # Synchronizing the ledger makes the reviewed watermark an exact export snapshot.
    revision = await exports._sync_export_ledger()
    watermark = exports._token({
        "v": exports.VERSION, "kind": "watermark", "position": [str(revision), ""],
    })
    metadata = _metadata()
    state = _load_state().get(f"{EXPORT_ID}:{exports.VERSION}", {})
    remote_id = state.get("dataset_id")
    return ContributionPreview(
        export_version=exports.VERSION,
        export_watermark=watermark,
        event=EventMetadata(
            slug="ndia-global-defense-hackathon-main-event-washington-dc",
            title="NDIA Global Defense Hackathon / Main Event: Washington, DC",
        ),
        metadata=metadata,
        confirmation_token=_confirmation_token(metadata, watermark, user),
        credential_configured=settings.ndia_key is not None,
        operator_authorization_configured=settings.ndia_catalog_operator_token is not None,
        publication_ready=(
            settings.ndia_key is not None
            and settings.ndia_catalog_operator_token is not None
            and settings.illuminate_public_url is not None
            and bool(settings.ndia_catalog_contribution_path)
        ),
        contribution_state=_truthful_state(state.get("contribution_state"), remote_id),
        remote_dataset_id=remote_id,
        message=(
            "This export version is already associated with a remote dataset."
            if remote_id else
            "Review the exact metadata and pass its confirmation token to submit."
        ),
    )


def _safe_portal_error(exc: Exception) -> PortalError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return PortalError(
            502, f"NDIA catalog rejected the contribution (HTTP {status})",
            uncertain=status >= 500,
        )
    if isinstance(exc, httpx.TimeoutException):
        return PortalError(504, "NDIA catalog timed out; remote outcome is uncertain", uncertain=True)
    return PortalError(502, "NDIA catalog is unavailable; use dry-run or retry later", uncertain=True)


async def _portal_request(
    method: str, path: str, *, body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if settings.ndia_key is None:
        raise HTTPException(503, "NDIA catalog credential is not configured; use dry-run")
    if not path:
        raise HTTPException(503, "NDIA catalog write endpoint is not configured; use dry-run")
    url = urljoin(settings.ndia_catalog_base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {
        settings.ndia_catalog_api_key_header: settings.ndia_key.get_secret_value(),
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with httpx.AsyncClient(timeout=settings.ndia_catalog_timeout_s) as client:
            response = await client.request(method, url, headers=headers, json=body)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise ValueError("expected object")
            return value
    except HTTPException:
        raise
    except Exception as exc:
        raise _safe_portal_error(exc) from exc


@router.get("/preview", response_model=ContributionPreview)
async def preview(user: str = Depends(user_id)):
    return await _preview(user)


def _authorize_operator(supplied: str | None) -> None:
    configured = settings.ndia_catalog_operator_token
    if configured is None:
        raise HTTPException(503, "catalog operator authorization is not configured; use dry-run")
    if supplied is None or not hmac.compare_digest(supplied, configured.get_secret_value()):
        raise HTTPException(403, "catalog operator authorization is required")


@router.post("/submit", response_model=ContributionResult)
async def submit(
    request: SubmitRequest,
    user: str = Depends(user_id),
    operator_token: str | None = Header(default=None, alias="X-Catalog-Operator"),
):
    current = await _preview(user)
    key = f"{EXPORT_ID}:{exports.VERSION}"
    async with _state_lock:
        state = _load_state()
        recorded = state.get(key, {})
        if recorded.get("dataset_id"):
            return ContributionResult(
                export_id=EXPORT_ID, export_version=exports.VERSION,
                dataset_id=recorded["dataset_id"],
                contribution_state=recorded.get("contribution_state", "submitted"),
                message="Already submitted; returning the recorded dataset identity.",
                dry_run=False, idempotent=True,
                submitted_at=recorded.get("submitted_at"), metadata=current.metadata,
            )
        _verify_confirmation(request.confirmation_token, current.metadata, current.export_watermark, user)
        if request.dry_run:
            return ContributionResult(
                export_id=EXPORT_ID, export_version=exports.VERSION,
                contribution_state="validated_dry_run",
                message="Schema-valid dry run completed; nothing was sent or recorded as published.",
                dry_run=True, metadata=current.metadata,
            )
        _authorize_operator(operator_token)
        if settings.ndia_key is None:
            raise HTTPException(503, "NDIA catalog credential is not configured; use dry-run")
        if settings.illuminate_public_url is None:
            raise HTTPException(503, "public dataset URL is not configured; use dry-run")
        if not settings.ndia_catalog_contribution_path:
            raise HTTPException(503, "NDIA catalog write endpoint is not configured; use dry-run")

        existing: dict[str, Any] = {}
        if settings.ndia_catalog_lookup_path:
            lookup_path = settings.ndia_catalog_lookup_path.format(
                event_id=EVENT_ID, export_id=EXPORT_ID, export_version=exports.VERSION,
            )
            try:
                existing = await _portal_request("GET", lookup_path)
            except HTTPException as exc:
                if recorded.get("contribution_state") in {"submitting", "unknown"}:
                    raise HTTPException(
                        409, "a prior submission has an uncertain outcome; reconcile it in the portal before retrying",
                    ) from exc
        elif recorded.get("contribution_state") in {"submitting", "unknown"}:
            raise HTTPException(
                409, "a prior submission has an uncertain outcome; configure lookup or reconcile it before retrying",
            )
        existing_id = existing.get("dataset_id") or existing.get("id")
        if existing_id:
            submitted_at = _now()
            record = {
                "dataset_id": str(existing_id),
                "contribution_state": str(existing.get("contribution_state") or existing.get("status") or "submitted"),
                "message": str(existing.get("message") or "Existing NDIA contribution reconciled."),
                "submitted_at": submitted_at.isoformat(),
                "export_watermark": current.export_watermark,
            }
            state[key] = record
            _save_state(state)
            return ContributionResult(
                export_id=EXPORT_ID, export_version=exports.VERSION,
                dataset_id=record["dataset_id"], contribution_state=record["contribution_state"],
                message=record["message"], dry_run=False, idempotent=True,
                submitted_at=submitted_at, metadata=current.metadata,
            )
        if recorded.get("contribution_state") in {"submitting", "unknown"}:
            raise HTTPException(
                409,
                "a prior submission has an uncertain outcome and lookup returned no "
                "dataset identity; reconcile it in the portal before retrying",
            )

        # This is the complete official dataset shape; publication bookkeeping
        # stays in local state and the idempotency header, not ad-hoc body fields.
        payload = current.metadata.model_dump(mode="json")
        idempotency_key = hashlib.sha256(key.encode()).hexdigest()
        state[key] = {
            "contribution_state": "submitting",
            "message": "Submission started; remote identity is pending.",
            "export_watermark": current.export_watermark,
            "idempotency_key": idempotency_key,
        }
        _save_state(state)
        try:
            remote = await _portal_request(
                "POST",
                settings.ndia_catalog_contribution_path.format(event_id=EVENT_ID),
                body=payload, idempotency_key=idempotency_key,
            )
        except HTTPException as exc:
            state = _load_state()
            if isinstance(exc, PortalError) and not exc.uncertain:
                state.pop(key, None)
            else:
                state[key]["contribution_state"] = "unknown"
                state[key]["message"] = "Remote outcome is uncertain; automatic retry is blocked."
            _save_state(state)
            raise
        dataset_id = remote.get("dataset_id") or remote.get("id")
        if not dataset_id:
            state = _load_state()
            pending = state.get(key, {})
            pending["contribution_state"] = "unknown"
            pending["message"] = (
                "NDIA catalog returned a malformed response without a dataset identity; "
                "automatic retry is blocked until lookup reconciliation."
            )
            state[key] = pending
            _save_state(state)
            raise HTTPException(502, "NDIA catalog response did not include a dataset ID")
        submitted_at = _now()
        record = {
            "dataset_id": str(dataset_id),
            "contribution_state": str(remote.get("contribution_state") or remote.get("status") or "submitted"),
            "message": str(remote.get("message") or "Contribution accepted by NDIA catalog."),
            "submitted_at": submitted_at.isoformat(),
            "export_watermark": current.export_watermark,
        }
        state[key] = record
        _save_state(state)
        return ContributionResult(
            export_id=EXPORT_ID, export_version=exports.VERSION,
            dataset_id=record["dataset_id"], contribution_state=record["contribution_state"],
            message=record["message"], dry_run=False, submitted_at=submitted_at,
            metadata=current.metadata,
        )


@router.get("/status", response_model=ContributionResult)
async def status(refresh: bool = False, user: str = Depends(user_id)):
    record = _load_state().get(f"{EXPORT_ID}:{exports.VERSION}", {})
    metadata = _metadata()
    dataset_id = record.get("dataset_id")
    if not dataset_id and refresh and record.get("contribution_state") in {"submitting", "unknown"}:
        if not settings.ndia_catalog_lookup_path:
            raise HTTPException(409, "lookup endpoint is not configured; reconcile the contribution in the portal")
        remote = await _portal_request(
            "GET",
            settings.ndia_catalog_lookup_path.format(
                event_id=EVENT_ID, export_id=EXPORT_ID, export_version=exports.VERSION,
            ),
        )
        dataset_id = remote.get("dataset_id") or remote.get("id")
        if dataset_id:
            record["dataset_id"] = str(dataset_id)
            record["contribution_state"] = str(remote.get("contribution_state") or remote.get("status") or "submitted")
            record["message"] = str(remote.get("message") or "Contribution reconciled.")
            async with _state_lock:
                state = _load_state()
                state[f"{EXPORT_ID}:{exports.VERSION}"] = record
                _save_state(state)
    if not dataset_id:
        return ContributionResult(
            export_id=EXPORT_ID, export_version=exports.VERSION,
            contribution_state=_truthful_state(record.get("contribution_state"), None),
            message=record.get("message", "No remote dataset is recorded for this export version."),
            dry_run=False, metadata=metadata,
        )
    if refresh:
        if not settings.ndia_catalog_status_path:
            raise HTTPException(503, "NDIA catalog status endpoint is not configured")
        remote = await _portal_request(
            "GET",
            settings.ndia_catalog_status_path.format(event_id=EVENT_ID, dataset_id=dataset_id),
        )
        record["contribution_state"] = str(remote.get("contribution_state") or remote.get("status") or record.get("contribution_state", "submitted"))
        record["message"] = str(remote.get("message") or record.get("message") or "Status refreshed.")
        async with _state_lock:
            state = _load_state()
            state[f"{EXPORT_ID}:{exports.VERSION}"] = record
            _save_state(state)
    return ContributionResult(
        export_id=EXPORT_ID, export_version=exports.VERSION,
        dataset_id=str(dataset_id), contribution_state=record.get("contribution_state", "submitted"),
        message=record.get("message", "Contribution identity is recorded."),
        dry_run=False, submitted_at=record.get("submitted_at"), metadata=metadata,
    )