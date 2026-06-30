from typing import cast

from sqlalchemy import Table

from app.models.click import Click


def test_click_model_has_expected_columns() -> None:
    table = cast(Table, Click.__table__)
    columns = table.columns.keys()

    assert "id" in columns
    assert "link_id" in columns
    assert "clicked_at" in columns
    assert "ip_anonymized" in columns
    assert "user_agent" in columns
    assert "browser" in columns
    assert "os" in columns
    assert "device_type" in columns
    assert "referrer" in columns
    assert "country" in columns
    assert "city" in columns


def test_click_model_has_phase3_indexes() -> None:
    table = cast(Table, Click.__table__)
    index_names = {index.name for index in table.indexes}

    assert "ix_clicks_link_id_clicked_at" in index_names
    assert "ix_clicks_clicked_at" in index_names
    assert "ix_clicks_link_id_country" in index_names
    assert "ix_clicks_link_id_browser" in index_names
    assert "ix_clicks_link_id_device_type" in index_names
