import asyncio
import time
from email.utils import formatdate

import httpx
import pytest
from illuminate.connectors import http

URL = 'https://api.gdeltproject.org/api/v2/doc/doc'

@pytest.fixture
def client_factory(monkeypatch, tmp_path):
    monkeypatch.setattr(http, '_cache_dir', tmp_path)
    monkeypatch.setattr(http, '_read_only_cache', False)
    monkeypatch.setattr(http, '_gdelt_lock', asyncio.Lock())
    monkeypatch.setattr(http, '_gdelt_cooldown_until', 0)
    monkeypatch.setattr(http, '_gdelt_requests', 0)
    monkeypatch.setattr(http, '_gdelt_last_status', None)
    monkeypatch.setattr(http, '_delays', {})
    monkeypatch.setattr(http, '_last_call', {})
    monkeypatch.setattr(http, '_throttle_locks', {})
    actual_client = httpx.AsyncClient
    def install(handler):
        monkeypatch.setattr(http.httpx, 'AsyncClient', lambda **kwargs: actual_client(transport=httpx.MockTransport(handler), **kwargs))
    return install

async def test_429_blocks_other_queries_until_cooldown_expires(client_factory, monkeypatch):
    responses = [httpx.Response(429, headers={'Retry-After': '120'}, text='rate limit'), httpx.Response(200, json={'articles': []})]
    client_factory(lambda request: responses.pop(0))
    with pytest.raises(http.HttpError) as first:
        await http.fetch_json('GET', URL, params={'query': 'flood'})
    assert first.value.retry_after == 120
    with pytest.raises(http.HttpError):
        await http.fetch_json('GET', URL, params={'query': 'earthquake'})
    assert http.gdelt_status()['requests_since_start'] == 1
    assert len(responses) == 1
    monkeypatch.setattr(http, '_gdelt_cooldown_until', time.time() - 1)
    assert await http.fetch_json('GET', URL) == {'articles': []}
    assert http.gdelt_status()['requests_since_start'] == 2

async def test_concurrent_identical_queries_share_cache(client_factory):
    active = 0
    async def handler(request):
        nonlocal active
        active += 1
        assert active == 1
        await asyncio.sleep(.01)
        active -= 1
        return httpx.Response(200, json={'articles': []})
    client_factory(handler)
    results = await asyncio.gather(*(http.fetch_json('GET', URL, params={'query': 'flood'}) for _ in range(3)))
    assert len(results) == 3
    assert http.gdelt_status()['requests_since_start'] == 1

async def test_cached_success_available_during_cooldown(client_factory, monkeypatch):
    client_factory(lambda request: httpx.Response(200, json={'articles': []}))
    await http.fetch_json('GET', URL)
    monkeypatch.setattr(http, '_gdelt_cooldown_until', time.time() + 60)
    assert await http.fetch_json('GET', URL) == {'articles': []}
    assert http.gdelt_status()['requests_since_start'] == 1

async def test_concurrent_throttle_waiters_remain_spaced(client_factory, monkeypatch):
    monkeypatch.setattr(http, '_delays', {http.GDELT_HOST: .025})
    started = []
    async def run():
        await http._throttle(http.GDELT_HOST)
        started.append(time.time())
    await asyncio.gather(*(run() for _ in range(4)))
    assert all(b - a >= .02 for a, b in zip(started, started[1:]))


def test_retry_after_supports_seconds_dates_and_missing_value(monkeypatch):
    monkeypatch.setattr(http.time, 'time', lambda: 1000000000)
    assert http._retry_seconds('120') == 120
    assert http._retry_seconds(formatdate(1000000180, usegmt=True)) == 180
    assert http._retry_seconds(None) == 60
    assert http._retry_seconds('garbage') == 60
