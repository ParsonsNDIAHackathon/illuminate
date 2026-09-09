"""The style contract (D6). Visual encoding is data the API returns, not CSS the
model writes. Fill/stroke are palette *names* from an allowlist; the frontend
resolves them to tokens with tested contrast on both grounds."""
from __future__ import annotations

from collections import OrderedDict
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PALETTE: dict[str, dict[str, str]] = {
    # name: light-ground fill / dark-ground fill. Both tested for contrast against label text.
    "purple": {"light": "#7c3aed", "dark": "#a78bfa"},
    "yellow": {"light": "#ca8a04", "dark": "#facc15"},
    "teal": {"light": "#0f766e", "dark": "#2dd4bf"},
    "orange": {"light": "#ea580c", "dark": "#fb923c"},
    "red": {"light": "#dc2626", "dark": "#f87171"},
    "green": {"light": "#15803d", "dark": "#4ade80"},
    "blue": {"light": "#1d4ed8", "dark": "#60a5fa"},
    "pink": {"light": "#be185d", "dark": "#f472b6"},
    "brown": {"light": "#92400e", "dark": "#d6a26b"},
    "neutral": {"light": "#6b7280", "dark": "#9ca3af"},
}
SWATCHES = list(PALETTE.keys())

StyleOpKind = Literal["clear", "set", "dim", "highlight", "hide"]


class StyleSpec(BaseModel):
    fill: str | None = None
    stroke: str | None = None
    badge: str | None = Field(default=None, max_length=24)
    size: Literal["sm", "md", "lg", "xl"] | None = None
    shape: Literal["ellipse", "rectangle", "diamond", "hexagon", "triangle"] | None = None
    dashed: bool | None = None

    @field_validator("fill", "stroke")
    @classmethod
    def _swatch(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if v not in PALETTE:
            # Unknown names fall back to neutral and warn (frontend does the same).
            return "neutral"
        return v


class StyleOp(BaseModel):
    op: StyleOpKind
    ids: list[str] = Field(default_factory=list)
    scope: Literal["all", "nodes", "edges"] | None = None
    style: StyleSpec | None = None
    label: str | None = Field(default=None, max_length=60)

    @field_validator("ids")
    @classmethod
    def _ids(cls, v):
        return [str(i) for i in v][:5000]


class LegendItem(BaseModel):
    swatch: str
    label: str
    count: int


def resolve_swatch(name: str | None) -> str:
    n = (name or "").strip().lower()
    return n if n in PALETTE else "neutral"


def validate_ops(raw: list[dict]) -> list[StyleOp]:
    return [StyleOp.model_validate(o) for o in raw]


def derive_legend(ops: list[StyleOp]) -> list[LegendItem]:
    """The legend is derived from the ops, never authored, so an encoding a user
    invented in one sentence arrives explained."""
    buckets: "OrderedDict[tuple[str, str], int]" = OrderedDict()
    for op in ops:
        if op.op == "clear":
            buckets.clear()
            continue
        if op.op not in ("set", "highlight") or not op.style:
            continue
        sw = resolve_swatch(op.style.fill or op.style.stroke)
        label = op.label or op.style.badge or sw.capitalize()
        key = (sw, label)
        buckets[key] = buckets.get(key, 0) + len(op.ids)
    return [LegendItem(swatch=k[0], label=k[1], count=n) for k, n in buckets.items()]


def style_contract_prompt() -> str:
    return (
        "STYLE OPS: to change how the graph is drawn, call set_styles with an ordered list of ops. "
        "op ∈ {clear, set, dim, highlight, hide}. 'set'/'highlight' take ids (element ids returned by a query) and a style "
        "{fill, stroke, badge, size, shape, dashed}. fill/stroke are palette NAMES only: "
        + ", ".join(SWATCHES)
        + ". Never emit hex or CSS. Give each 'set' a short label — the legend is derived from your ops.\n"
        "STYLING IS CUMULATIVE and persists across turns. Your ops are added to the encodings already on the "
        "canvas; they do not replace them. So send only what this turn adds — never restate an encoding from an "
        "earlier turn, and never open with 'clear' to make room. Emit 'clear' only when the user actually asks to "
        "reset or start over. If the user muted the graph two turns ago and now asks to colour something, send just "
        "the colour: the mute is still there, and painting an element lifts the mute off that element.\n"
        "'dim' and 'hide' may give a scope {all, nodes, edges} with no ids, which addresses everything in that "
        "scope — that is how 'mute everything' or 'dim the graph' is expressed, and it does not need a query first. "
        "'set' and 'highlight' always need ids."
    )
