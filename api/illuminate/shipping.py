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
    kind: Literal["port", "hub", "intermodal"] = "port"
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country: str = Field(min_length=2, max_length=2)


class Source(Record):
    title: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class Segment(Record):
    mode: Literal["ocean", "truck", "rail"] = "ocean"
    source: Source | None = None
    from_port: str
    to_port: str
    waypoints: list[Point] = Field(default_factory=list, max_length=100)
    passages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_transport(self):
        import re
        if self.mode != "ocean" and (not self.source or not self.passages):
            raise ValueError("Domestic legs require a corridor name and source")
        if self.mode == "truck" and any(not re.fullmatch(r"I-[1-9][0-9]{0,2}", name) for name in self.passages):
            raise ValueError("Trucking legs must identify Interstate highways only")
        return self


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
        ports = {p.id: p for p in self.ports}
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
                endpoints = [ports[segment.from_port], ports[segment.to_port]]
                if segment.mode == "ocean" and any(p.kind != "port" for p in endpoints):
                    raise ValueError("Ocean legs must connect ports")
                if segment.mode != "ocean" and any(p.country != "US" for p in endpoints):
                    raise ValueError("Domestic legs must connect US endpoints")
                if segment.from_port == segment.to_port:
                    raise ValueError("A segment must connect different ports")
                if i and route.segments[i - 1].to_port != segment.from_port:
                    raise ValueError("Route segments must form a continuous journey")
        return self


class Corridor(Record):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    mode: Literal["truck", "rail"]
    stops: list[str] = Field(min_length=2)
    points: list[Point] = Field(min_length=2, max_length=200)
    source: Source
    updated_at: date
    notes: str = Field(min_length=1)


class TransportNetwork(Record):
    corridors: list[Corridor]

    @model_validator(mode="after")
    def validate_corridors(self):
        import re
        if len({c.id for c in self.corridors}) != len(self.corridors):
            raise ValueError("Corridor IDs must be unique")
        for c in self.corridors:
            if len(c.stops) != len(c.points):
                raise ValueError("Each named stop must have a point")
            if c.mode == "truck" and not re.fullmatch(r"I-[1-9][0-9]{0,2}", c.name):
                raise ValueError("The US highway layer supports Interstate corridors only")
            if any(not (24 <= p.latitude <= 50 and -125 <= p.longitude <= -66) for p in c.points):
                raise ValueError("US corridors must stay within the contiguous-US map extent")
            if c.updated_at > date.today():
                raise ValueError("Corridor update date cannot be in the future")
        return self
