from app.tasks.celery_app import celery_app


def test_celery_app_uses_expected_broker_and_backend():
    assert celery_app.conf.broker_url
    assert celery_app.conf.result_backend


def test_celery_includes_expected_tasks():
    includes = set(celery_app.conf.include)

    assert "app.tasks.health" in includes
    assert "app.tasks.analytics" in includes
