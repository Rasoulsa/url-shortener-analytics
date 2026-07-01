from app.core.config import settings
from app.tasks.celery_app import celery_app


def test_celery_app_uses_expected_broker_and_backend():
    assert celery_app.conf.broker_url
    assert celery_app.conf.result_backend


def test_celery_includes_expected_tasks():
    includes = set(celery_app.conf.include)

    assert "app.tasks.health" in includes
    assert "app.tasks.analytics" in includes


def test_celery_beat_schedules_click_counter_flush() -> None:
    schedule = celery_app.conf.beat_schedule

    assert "flush-click-counters-every-30-seconds" in schedule
    assert (
        schedule["flush-click-counters-every-30-seconds"]["task"]
        == "analytics.flush_click_counters"
    )
    assert (
        schedule["flush-click-counters-every-30-seconds"]["schedule"]
        == settings.click_counter_flush_seconds
    )
