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
        assert kwargs['params']['timespan'] == '3d'
        assert kwargs['params']['sort'] == 'datedesc'
        assert kwargs['params']['query'] == 'flood'
        assert kwargs['ttl'] == 300
        return {'articles': [
            {'url': 'https://example.com/news', 'title': 'Flood in Nepal'},
            {'url': 'https://example.com/news'},
            {'url': 'javascript:alert(1)'}, None,
        ]}
    monkeypatch.setattr(news, 'fetch_json', fetch)
    response = client.get('/api/news', params={'query': ' flood ', 'timespan': '3d'})
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


def test_rate_limit_recovers_with_one_delayed_retry(monkeypatch):
    calls = []
    delays = []
    async def fetch(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise HttpError(429, 'https://example.com')
        return {'articles': [{'url': 'https://example.com/news', 'title': 'Flood in Nepal'}]}
    async def pause(seconds):
        delays.append(seconds)
    monkeypatch.setattr(news, 'fetch_json', fetch)
    monkeypatch.setattr(news, 'sleep', pause)
    response = client.get('/api/news')
    assert response.status_code == 200
    assert len(response.json()['articles']) == 1
    assert len(calls) == 2
    assert delays == [6]
