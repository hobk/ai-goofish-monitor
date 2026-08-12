import json

from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.active_inquiry_service import (
    create_inquiry_from_result_item,
    ensure_active_inquiry_schema,
    get_inquiry,
)


def test_create_inquiry_from_result_item_uses_history_record_even_when_module_disabled(tmp_path, monkeypatch):
    db_path = tmp_path / "app.sqlite3"
    monkeypatch.setenv("APP_DATABASE_FILE", str(db_path))
    ensure_active_inquiry_schema()
    record = {
        "搜索关键字": "大疆neo2畅飞套装",
        "任务名称": "大疆neo2畅飞套装",
        "商品信息": {
            "商品ID": "item-1",
            "商品标题": "AI推荐历史商品",
            "当前售价": "¥2000",
            "商品链接": "https://www.goofish.com/item?id=item-1",
        },
        "卖家信息": {"卖家ID": "seller-1", "卖家昵称": "卖家A"},
        "ai_analysis": {"is_recommended": True, "value_score": 82, "analysis_source": "ai"},
    }
    with sqlite_connection(str(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO result_items (
                result_filename, keyword, task_name, crawl_time, price, price_display,
                item_id, title, link, link_unique_key, seller_nickname, is_recommended,
                analysis_source, keyword_hit_count, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test_full_data.jsonl",
                "大疆neo2畅飞套装",
                "大疆neo2畅飞套装",
                "2026-08-12T00:00:00",
                2000,
                "¥2000",
                "item-1",
                "AI推荐历史商品",
                "https://www.goofish.com/item?id=item-1",
                "item:item-1",
                "卖家A",
                1,
                "ai",
                0,
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()

    inquiry_id = create_inquiry_from_result_item("test_full_data.jsonl", "item-1", auto_start=False)

    inquiry = get_inquiry(inquiry_id)
    assert inquiry is not None
    assert inquiry["item_id"] == "item-1"
    assert inquiry["seller_id"] == "seller-1"
    assert inquiry["score"] == 82
