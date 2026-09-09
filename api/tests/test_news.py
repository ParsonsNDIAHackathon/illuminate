import httpx
import pytest
import json
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from illuminate.routers import news
from illuminate.connectors.http import HttpError
from illuminate.connectors import http

app = FastAPI()
app.include_router(news.router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_news_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(http, '_cache_dir', tmp_path)
    monkeypatch.setattr(http, '_read_only_cache', False)
    news._retry_after.clear()
    yield
    news._retry_after.clear()


def save_news(query='flood', timespan='24h', age=30):
    params = {'query': query, 'mode': 'artlist', 'format': 'json', 'maxrecords': 250, 'timespan': timespan, 'sort': 'datedesc'}
    url = str(httpx.Request('GET', news.DOC, params=params).url)
    doc = {'_ts': time.time() - age, 'url': url, 'body': {'articles': [{'url': 'https://example.com/saved', 'title': 'Saved flood coverage'}]}}
    path = http.cache_dir() / f"{http._key('GET', url, None)}.json"
    path.write_text(json.dumps(doc))
    return path, doc


def test_news_search_normalizes_and_deduplicates(monkeypatch):
    async def fetch(method, url, **kwargs):
        assert kwargs['params']['timespan'] == '3d'
        assert kwargs['params']['sort'] == 'datedesc'
        assert kwargs['params']['query'] == 'flood'
        assert kwargs['ttl'] == 900
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


def test_disk_cache_survives_new_clients_without_upstream_requests(monkeypatch):
    _, saved = save_news()
    async def fail(*args, **kwargs):
        pytest.fail('fresh cache must not contact GDELT')
    monkeypatch.setattr(news, 'fetch_json', fail)
    first = client.get('/api/news?query=flood').json()
    second = TestClient(app).get('/api/news?query=%20flood%20').json()
    assert first == second
    assert first['cached'] is True and first['stale'] is False
    assert first['articles'][0]['title'] == 'Saved flood coverage'
    assert first['fetched_at'] == news.datetime.fromtimestamp(saved['_ts'], news.timezone.utc).isoformat()


@pytest.mark.parametrize('error', [HttpError(429, 'https://example.com'), httpx.ReadTimeout('timeout'), HttpError(200, 'https://example.com')])
def test_stale_fallback_preserves_date_and_backs_off_on_errors(monkeypatch, error):
    path, saved = save_news(age=1800)
    calls = []
    async def fail(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(news, 'fetch_json', fail)
    first = client.get('/api/news?query=flood')
    assert first.status_code == 200
    body = first.json()
    assert body['cached'] and body['stale']
    assert body['notice'] and body['articles']
    assert client.get('/api/news?query=flood').json() == body
    assert len(calls) == 1
    assert json.loads(path.read_text())['_ts'] == saved['_ts']


def test_queries_and_time_windows_have_separate_cache_entries(monkeypatch):
    save_news()
    calls = []
    async def fetch(*args, **kwargs):
        calls.append(kwargs['params'])
        return {'articles': []}
    monkeypatch.setattr(news, 'fetch_json', fetch)
    assert client.get('/api/news?query=earthquake').json()['articles'] == []
    assert client.get('/api/news?query=flood&timespan=7d').json()['articles'] == []
    assert len(calls) == 2


def test_cache_older_than_seven_days_is_not_presented_as_recent_coverage(monkeypatch):
    save_news(age=8 * 86400)
    async def fail(*args, **kwargs):
        raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(news, 'fetch_json', fail)
    assert client.get('/api/news?query=flood').status_code == 504


async def test_malformed_refresh_cannot_overwrite_last_good_disk_response(monkeypatch):
    path, saved = save_news(age=1800)
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={'error': 'not an article response'}))
    monkeypatch.setattr(http.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=transport, **kwargs))
    async def no_delay(*args): pass
    monkeypatch.setattr(http, '_throttle', no_delay)
    params = dict(httpx.URL(saved['url']).params)
    with pytest.raises(HttpError):
        await http.fetch_json('GET', news.DOC, params=params, ttl=900, validate=news._valid)
    assert json.loads(path.read_text()) == saved
