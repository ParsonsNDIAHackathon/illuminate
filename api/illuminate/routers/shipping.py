"""Read-only catalog; illustrative records never become graph assertions."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..config import settings
from ..shipping import ShippingCatalog

router = APIRouter(prefix="/api/shipping", tags=["shipping"])


@router.get("", response_model=ShippingCatalog)
async def shipping_catalog():
    path = settings.data_dir / "shipping.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / "shipping_demo.json"
    try:
        return ShippingCatalog.model_validate_json(path.read_text())
    except (OSError, ValidationError) as exc:
        raise HTTPException(503, "Shipping data could not be loaded. Check the shipping catalog and retry.") from exc
