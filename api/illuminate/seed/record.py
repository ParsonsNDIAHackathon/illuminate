"""Re-run one connector against the seed's fixture cache, recording any response it
does not have yet, without touching Neo4j.

    python -m illuminate.seed.record littlesis            # names from the existing search fixtures
    python -m illuminate.seed.record littlesis "RTX" ...  # explicit names

A connector grows (LittleSis gained ownership, memberships, lobbying and each officer's
other seats); the offline seed can only show what the fixtures hold. This replays the
connector for the names the seed already searched, so the new calls land in
seed/fixtures and `make seed` stays a no-network build. Responses already cached are
reused whatever their age, so a re-record only adds files.
"""
from __future__ import annotations

import asyncio
import functools
import json
import sys
import time
from urllib.parse import parse_qs, urlparse

from ..connectors import get_connector
from ..connectors import http
from ..ids import entity_id
from .seed import FIXTURES

HOSTS = {"littlesis": "littlesis.org"}


def seeded_names(host: str) -> list[str]:
    """The names the seed searched at this host, in fixture order."""
    names: list[str] = []
    for p in sorted(FIXTURES.glob("*.json")):
        try:
            url = json.loads(p.read_text()).get("url") or ""
        except Exception:
            continue
        u = urlparse(url)
        if host in (u.netloc or "") and u.path.endswith("/search"):
            q = parse_qs(u.query).get("q", [])
            if q:
                names.append(q[0])
    return list(dict.fromkeys(names))


async def record(connector_name: str, names: list[str]) -> None:
    conn = get_connector(connector_name)
    if not conn:
        sys.exit(f"no connector {connector_name!r}")
    http.set_cache_dir(FIXTURES, read_only=False)
    # Cached responses stay valid regardless of age: this adds fixtures, it does not refresh them.
    http.fetch_json = functools.partial(http.fetch_json, ttl=10 * 365 * 86400)  # type: ignore[assignment]
    mod = sys.modules[type(conn).__module__]
    if hasattr(mod, "fetch_json"):
        mod.fetch_json = http.fetch_json  # the connector imported the name directly
    before = len(list(FIXTURES.glob("*.json")))
    t0 = time.time()
    for i, name in enumerate(names, 1):
        ent = {"id": entity_id(name=name), "name": name, "kind": "organization"}
        try:
            facts = await conn.enrich(ent, "local")
        except Exception as e:  # keep going; a throttled call is retried by the connector itself
            print(f"[{i}/{len(names)}] {name}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            continue
        preds: dict[str, int] = {}
        for f in facts:
            preds[f.predicate] = preds.get(f.predicate, 0) + 1
        print(f"[{i}/{len(names)}] {name}: {len(facts)} facts {json.dumps(preds, sort_keys=True)}", flush=True)
    after = len(list(FIXTURES.glob("*.json")))
    print(f"recorded {after - before} new fixtures in {time.time() - t0:.0f}s ({after} total)")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    connector_name = sys.argv[1]
    names = sys.argv[2:] or seeded_names(HOSTS.get(connector_name, connector_name))
    asyncio.run(record(connector_name, names))


if __name__ == "__main__":
    main()
