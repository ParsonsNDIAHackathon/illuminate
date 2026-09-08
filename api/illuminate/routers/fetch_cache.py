from __future__ import annotations

import hmac
import base64
import hashlib
import json

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..config import settings
from .. import fetch_cache
from ..connectors.http import (
    MAX_SHARED_PAYLOAD_BYTES,
    _split_body_credentials,
    scrub,
)

router = APIRouter(prefix="/api/fetch-cache", tags=["operations"])
MAX_CACHE_PAYLOAD_BYTES = MAX_SHARED_PAYLOAD_BYTES
MAX_CACHE_PAYLOAD_B64 = 4 * ((MAX_CACHE_PAYLOAD_BYTES + 2) // 3)


async def _authorize(authorization: str | None) -> None:
    if not settings.illuminate_fetch_cache_authority_enabled:
        raise HTTPException(status_code=503, detail="cache authority is not enabled")
    configured = settings.illuminate_fetch_cache_token or settings.session_secret
    if configured is None or not configured.get_secret_value():
        raise HTTPException(status_code=503, detail="cache service is not configured")
    expected = f"Bearer {configured.get_secret_value()}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="cache service authentication required")
    if not fetch_cache.schema_ready():
        try:
            await fetch_cache.ensure_schema()
        except Exception:
            raise HTTPException(status_code=503, detail="cache authority storage is not ready") from None
    if not fetch_cache.schema_ready():
        raise HTTPException(status_code=503, detail="cache authority storage is not ready")


class ClaimRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=100)
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    lease_s: float = Field(default=45, ge=1, le=300)


class PublishRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=100)
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner: str = Field(min_length=1, max_length=64)
    fence: int = Field(ge=1)
    record: "CacheRecord"

    @model_validator(mode="after")
    def validate_identity(self):
        try:
            request = json.loads(self.record.request)
        except Exception:
            raise ValueError("invalid canonical request metadata") from None
        required = {
            "source", "method", "url", "body", "representation", "contract",
            "credential_scope",
        }
        if not isinstance(request, dict) or set(request) != required:
            raise ValueError("invalid canonical request fields")
        if request["source"] != self.record.source:
            raise ValueError("cache source does not match request identity")
        if not all(isinstance(request[name], str) and request[name] for name in (
            "source", "method", "url", "representation", "contract",
        )):
            raise ValueError("invalid canonical request values")
        scope = request["credential_scope"]
        if scope is not None and (
            not isinstance(scope, str) or len(scope) != 64
            or any(character not in "0123456789abcdef" for character in scope)
        ):
            raise ValueError("invalid credential scope fingerprint")
        if scrub(request["url"]) != request["url"]:
            raise ValueError("cache request URL contains credential material")
        clean_body, body_credentials = _split_body_credentials(request["body"])
        if body_credentials or clean_body != request["body"]:
            raise ValueError("cache request body contains credential material")
        canonical = json.dumps(
            request, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        if canonical != self.record.request:
            raise ValueError("request metadata is not canonical")
        if hashlib.sha256(canonical.encode()).hexdigest() != self.identity:
            raise ValueError("cache identity does not match request metadata")
        return self


class CacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    request: str = Field(min_length=2, max_length=65536)
    final_url: str = Field(min_length=1, max_length=4096)
    content_type: str = Field(max_length=500)
    truncated: bool
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_b64: str = Field(max_length=MAX_CACHE_PAYLOAD_B64)
    x_frame_options: str | None = Field(default=None, max_length=1000)
    content_security_policy: str | None = Field(default=None, max_length=16000)

    @model_validator(mode="after")
    def validate_payload(self):
        try:
            payload = base64.b64decode(self.payload_b64, validate=True)
            request = json.loads(self.request)
        except Exception:
            raise ValueError("invalid cache record encoding") from None
        if len(payload) > MAX_CACHE_PAYLOAD_BYTES:
            raise ValueError("cache payload exceeds byte limit")
        if hashlib.sha256(payload).hexdigest() != self.content_hash:
            raise ValueError("cache content hash does not match payload")
        if not isinstance(request, dict):
            raise ValueError("cache request metadata must be an object")
        if scrub(self.final_url) != self.final_url:
            raise ValueError("cache final URL contains credential material")
        return self


class RenewRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=100)
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner: str = Field(min_length=1, max_length=64)
    fence: int = Field(ge=1)
    lease_s: float = Field(default=45, ge=1, le=300)


class ReleaseRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=100)
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner: str = Field(min_length=1, max_length=64)
    fence: int = Field(ge=1)
    retry_after_s: float = Field(default=10, ge=1, le=300)


@router.get("/records/{namespace}/{identity}")
async def read_record(namespace: str, identity: str, authorization: str | None = Header(None)):
    await _authorize(authorization)
    record = await fetch_cache.get_record(namespace, identity)
    if record is None:
        raise HTTPException(status_code=404, detail="not found")
    return record


@router.post("/claim")
async def acquire(body: ClaimRequest, authorization: str | None = Header(None)):
    await _authorize(authorization)
    return await fetch_cache.claim(body.namespace, body.identity, body.lease_s)


@router.post("/publish")
async def publish(body: PublishRequest, authorization: str | None = Header(None)):
    await _authorize(authorization)
    try:
        return await fetch_cache.publish(
            body.namespace, body.identity, body.owner, body.fence,
            body.record.model_dump(exclude_none=True),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/renew")
async def renew(body: RenewRequest, authorization: str | None = Header(None)):
    await _authorize(authorization)
    try:
        lease_until = await fetch_cache.renew(
            body.namespace, body.identity, body.owner, body.fence, body.lease_s,
        )
        return {"lease_until": lease_until}
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/release", status_code=204)
async def release(body: ReleaseRequest, authorization: str | None = Header(None)):
    await _authorize(authorization)
    await fetch_cache.release(
        body.namespace, body.identity, body.owner, body.fence,
        retry_after_s=body.retry_after_s,
    )