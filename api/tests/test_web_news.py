from datetime import datetime, timezone
import httpx
import pytest
from fastapi import HTTPException
from illuminate.connectors import web_news
from illuminate.routers import news

NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
FEED = b'''<rss><channel><item><title>Flood in Nepal - Example</title>
<link>https://news.google.com/rss/articles/one</link><pubDate>Wed, 09 Sep 2026 10:00:00 GMT</pubDate>
<source url="https://example.com">Example</source></item>
<item><title>Old coverage</title><link>https://example.com/old</link><pubDate>Mon, 01 Sep 2025 10:00:00 GMT</pubDate></item>
<item><title>Bad link</title><link>javascript:alert(1)</link><pubDate>Wed, 09 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>'''


def test_rss_preserves_provenance_and_enforces_dates():
    articles = web_news.parse_feed(FEED, '24h', NOW)
    assert len(articles) == 1
    assert articles[0]['title'] == 'Flood in Nepal'
    assert articles[0]['domain'] == 'example.com'
    assert articles[0]['published_at'] == '2026-09-09T10:00:00+00:00'
    assert articles[0]['seendate'] == ''


@pytest.mark.parametrize('body', [b'<html/>', b'<!DOCTYPE rss><rss/>', b'x' * 2_000_001])
def test_invalid_rss_rejected(body):
    with pytest.raises(ValueError): web_news.parse_feed(body, '24h', NOW)


def article(url='https://example.com/a', provider='GDELT'):
    return {'url': url, 'title': 'Flood in Nepal', 'domain': 'example.com', 'seendate': '20260909T100000Z', 'provider': provider, 'providers': [provider]}


def test_duplicate_web_results_merge_sources():
    result = news.merge_articles([[article()], [article('https://news.google.com/rss/articles/a', 'Google News')]])
    assert len(result) == 1
    assert result[0]['providers'] == ['GDELT', 'Google News']
    assert result[0]['url'] == 'https://example.com/a'
    assert len(news.merge_articles([[article()], [article('https://example.com/a?utm_source=x')]])) == 1


@pytest.mark.parametrize('failed', ['GDELT', 'Google News', 'both'])
async def test_partial_failure_keeps_other_provider(monkeypatch, failed):
    async def gdelt(*args):
        if failed in ('GDELT', 'both'): raise HTTPException(503, 'rate limit')
        return {'articles': [article()], 'fetched_at': NOW.isoformat()}
    async def google(*args):
        if failed in ('Google News', 'both'): raise httpx.ReadTimeout('timeout')
        return {'articles': [article(provider='Google News')], '_ts': NOW.timestamp()}
    monkeypatch.setattr(news, 'search_news', gdelt)
    monkeypatch.setattr(news, 'search_web_news', google)
    if failed == 'both':
        with pytest.raises(HTTPException) as exc: await news.search_all_news('flood', '24h')
        assert exc.value.status_code == 503
    else:
        result = await news.search_all_news('flood', '24h')
        assert len(result['articles']) == 1
        assert failed + ' is unavailable' in result['notice']
        assert any(s['status'] == 'ok' for s in result['sources'])


async def test_google_cache_and_stale_fallback(monkeypatch):
    web_news._cache.clear()
    key = ('flood', '24h')
    import time
    saved = {'articles': [article(provider='Google News')], '_ts': time.time(), 'cached': False, 'stale': False}
    web_news._cache[key] = saved
    assert (await web_news.search_web_news(*key))['cached']
    saved['_ts'] -= 1000
    async def fail(*args, **kwargs): raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr(httpx.AsyncClient, '__aenter__', fail)
    fallback = await web_news.search_web_news(*key)
    assert fallback['stale']
    assert fallback['_ts'] == saved['_ts']
    web_news._cache.clear()


async def test_google_preserves_multi_topic_query(monkeypatch):
    web_news._cache.clear()
    def respond(request):
        assert request.url.params['q'] == '(flood OR earthquake) when:1d'
        return httpx.Response(200, content=b'<rss><channel/></rss>')
    client_type = httpx.AsyncClient
    monkeypatch.setattr(web_news.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    result = await web_news.search_web_news('(flood OR earthquake)', '24h')
    assert result['articles'] == []
    web_news._cache.clear()
