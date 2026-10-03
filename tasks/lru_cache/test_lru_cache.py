from lru_cache import LRUCache


def test_evicts_the_least_recently_used_key():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert "a" not in cache
    assert cache.get("b") == 2 and cache.get("c") == 3


def test_get_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)  # "b" is now the least recently used
    assert "b" not in cache and "a" in cache


def test_update_refreshes_recency():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    cache.put("c", 3)
    assert "b" not in cache and cache.get("a") == 10


def test_missing_key_returns_default():
    assert LRUCache(1).get("x", "miss") == "miss"
