"""Shipping overlay records, kept separate from asserted graph facts and risk scores."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Point(Record):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class Port(Point):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)


class Source(Record):
    title: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class Segment(Record):
    from_port: str
    to_port: str
    waypoints: list[Point] = Field(default_factory=list, max_length=100)
    passages: list[str] = Field(default_factory=list)


class Route(Record):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    relationship_id: str = Field(min_length=1)
    goods: str = Field(min_length=1)
    status: Literal["confirmed", "inferred", "illustrative"]
    source: Source
    updated_at: date
    notes: str = Field(min_length=1)
    segments: list[Segment] = Field(min_length=1, max_length=30)


class ShippingCatalog(Record):
    ports: list[Port]
    routes: list[Route]

    @model_validator(mode="after")
    def validate_links(self):
        ports = {p.id for p in self.ports}
        if len(ports) != len(self.ports) or len({r.id for r in self.routes}) != len(self.routes):
            raise ValueError("Port and route IDs must be unique")
        for route in self.routes:
            if route.supplier_id == route.customer_id:
                raise ValueError("Supplier and customer must differ")
            if route.updated_at > date.today():
                raise ValueError("Route update date cannot be in the future")
            for i, segment in enumerate(route.segments):
                if segment.from_port not in ports or segment.to_port not in ports:
                    raise ValueError("Every segment must reference known ports")
                if segment.from_port == segment.to_port:
                    raise ValueError("A segment must connect different ports")
                if i and route.segments[i - 1].to_port != segment.from_port:
                    raise ValueError("Route segments must form a continuous journey")
        return self
