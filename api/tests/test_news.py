import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from illuminate.routers import news
from illuminate.connectors.http import HttpError

app = FastAPI()
app.include_router(news.router)
client = TestClient(app)


def test_news_search_normalizes_and_deduplicates(monkeypatch):
    async def fetch(method, url, **kwargs):
        assert kwargs['params']['timespan'] == '1m'
        assert kwargs['params']['sort'] == 'datedesc'
        assert kwargs['params']['query'] == 'flood'
        assert kwargs['ttl'] == 300
        return {'articles': [
            {'url': 'https://example.com/news', 'title': 'Flood in Nepal'},
            {'url': 'https://example.com/news'},
            {'url': 'javascript:alert(1)'}, None,
        ]}
    monkeypatch.setattr(news, 'fetch_json', fetch)
    response = client.get('/api/news', params={'query': ' flood ', 'timespan': '1m'})
    assert response.status_code == 200
    assert len(response.json()['articles']) == 1
    assert response.json()['articles'][0]['title'] == 'Flood in Nepal'


@pytest.mark.parametrize('params', [{'query': '  '}, {'query': 'x'}, {'timespan': '30d'}])
def test_invalid_search(params):
    assert client.get('/api/news', params=params).status_code == 422


@pytest.mark.parametrize('error,status', [
    (HttpError(429, 'https://example.com'), 503),
    (HttpError(200, 'https://example.com', 'non-JSON response'), 502),
    (httpx.ReadTimeout('timeout'), 504),
])
def test_upstream_errors(monkeypatch, error, status):
    async def fetch(*args, **kwargs):
        raise error
    monkeypatch.setattr(news, 'fetch_json', fetch)
    assert client.get('/api/news').status_code == status


def test_empty_and_malformed_results(monkeypatch):
    async def empty(*args, **kwargs):
        return {'articles': []}
    monkeypatch.setattr(news, 'fetch_json', empty)
    assert client.get('/api/news').json()['articles'] == []
    async def malformed(*args, **kwargs):
        return {'error': 'query not accepted'}
    monkeypatch.setattr(news, 'fetch_json', malformed)
    assert client.get('/api/news').status_code == 502


def test_rate_limit_returns_cooldown_without_retry(monkeypatch):
    calls = []
    async def fetch(*args, **kwargs):
        calls.append(kwargs)
        raise HttpError(429, 'https://example.com', retry_after=120)
    monkeypatch.setattr(news, 'fetch_json', fetch)
    response = client.get('/api/news')
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '120'
    assert len(calls) == 1


def test_long_search_windows_span_calendar_months():
    from datetime import datetime, timezone
    now = datetime(2026, 8, 31, 12, 17, tzinfo=timezone.utc)
    for span, count, start in [('12m', 4, '20250831121500')]:
        windows = news.search_windows(span, now)
        assert len(windows) == count
        assert sum(w['maxrecords'] for w in windows) == 250
        assert windows[0]['enddatetime'] == '20260831121500'
        assert windows[-1]['startdatetime'] == start
        assert all(a['startdatetime'] == b['enddatetime'] for a, b in zip(windows, windows[1:]))


@pytest.mark.parametrize('span,count', [('7d', 1), ('1m', 1), ('3m', 1), ('12m', 4)])
def test_all_time_windows_search_and_merge(monkeypatch, span, count):
    calls = []
    async def fetch(*args, **kwargs):
        calls.append(kwargs['params'])
        return {'articles': [{'url': 'https://example.com/shared', 'title': 'Shared'},
                             {'url': f'https://example.com/{len(calls)}', 'title': 'Article'}]}
    monkeypatch.setattr(news, 'fetch_json', fetch)
    response = client.get('/api/news', params={'timespan': span})
    assert response.status_code == 200
    assert len(calls) == count
    if span == '3m':
        assert calls[0]['timespan'] == '3m'
        assert calls[0]['maxrecords'] == 250
        assert 'startdatetime' not in calls[0]
    assert len(response.json()['articles']) == count + 1
    assert response.json()['timespan'] == span
