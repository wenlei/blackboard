import pytest


@pytest.fixture(scope="session")
def redis_available():
    try:
        import redis
        r = redis.Redis()
        r.ping()
        return True
    except Exception:
        return False
