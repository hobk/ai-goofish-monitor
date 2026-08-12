from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.infrastructure.external.ai_client import AIClient
from src.services.active_inquiry_im import ActiveInquiryImClient, cookies_from_storage_state, IncomingMessage
from src.ai_handler import send_ntfy_notification

DEFAULT_PROMPT_FILE = "prompts/active_inquiry_prompt.txt"
DEFAULT_SETTINGS = {
    "enabled": False,
    "threshold": 70,
    "max_rounds": 6,
    "bargain_percent": 10,
    "prompt_file": DEFAULT_PROMPT_FILE,
    "account_state_file": "",
    "auto_send": True,
    "captcha_solver_enabled": False,
    "captcha_solver_endpoint": "",
    "captcha_solver_api_key": "",
    "captcha_solver_pass_cookies": True,
    "captcha_solver_timeout": 60,
}

_RUNTIME: Optional["ActiveInquiryRuntime"] = None


def extract_recommendation_score(analysis: dict) -> int:
    if not isinstance(analysis, dict):
        return 0
    for key in ("recommendation_score", "recommend_score", "score", "value_score", "confidence"):
        value = analysis.get(key)
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(value))))
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if match:
            return max(0, min(100, int(round(float(match.group(0))))))
    return 100 if analysis.get("is_recommended") else 0


def should_start_inquiry(record: dict, settings: dict, *, ignore_enabled: bool = False) -> bool:
    if not ignore_enabled and not settings.get("enabled"):
        return False
    analysis = record.get("ai_analysis", {}) or {}
    if analysis.get("is_recommended") is False:
        return False
    return extract_recommendation_score(analysis) >= int(settings.get("threshold", 70) or 70)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def _json_loads(text: str, default):
    try:
        return json.loads(text or "")
    except Exception:
        return default


SECRET_MASK = "********"


def mask_secret_value(value: str | None) -> str:
    return SECRET_MASK if str(value or "").strip() else ""


def public_settings(settings: dict) -> dict:
    visible = dict(settings)
    visible["captcha_solver_api_key"] = mask_secret_value(visible.get("captcha_solver_api_key"))
    return visible


def merge_settings_payload(payload: dict, existing: dict | None = None) -> dict:
    settings = {**DEFAULT_SETTINGS, **(existing or {}), **payload}
    if str(payload.get("captcha_solver_api_key") or "") == SECRET_MASK:
        settings["captcha_solver_api_key"] = (existing or {}).get("captcha_solver_api_key", "")
    return settings


def _migrate_settings_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(active_inquiry_settings)").fetchall()}
    additions = {
        "captcha_solver_enabled": "INTEGER NOT NULL DEFAULT 0",
        "captcha_solver_endpoint": "TEXT NOT NULL DEFAULT ''",
        "captcha_solver_api_key": "TEXT NOT NULL DEFAULT ''",
        "captcha_solver_pass_cookies": "INTEGER NOT NULL DEFAULT 1",
        "captcha_solver_timeout": "INTEGER NOT NULL DEFAULT 60",
    }
    for name, ddl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE active_inquiry_settings ADD COLUMN {name} {ddl}")


def ensure_active_inquiry_schema() -> None:
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS active_inquiry_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL,
            threshold INTEGER NOT NULL,
            max_rounds INTEGER NOT NULL,
            bargain_percent REAL NOT NULL,
            prompt_file TEXT NOT NULL,
            account_state_file TEXT,
            auto_send INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        _migrate_settings_columns(conn)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS active_inquiries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_item_id INTEGER,
            item_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            seller_nickname TEXT,
            task_name TEXT,
            keyword TEXT,
            title TEXT,
            price REAL,
            target_price REAL,
            score INTEGER NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            chat_id TEXT,
            account_id TEXT,
            rounds INTEGER NOT NULL DEFAULT 0,
            item_json TEXT NOT NULL,
            context_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(item_id, seller_id)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS active_inquiry_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inquiry_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            raw_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(inquiry_id) REFERENCES active_inquiries(id) ON DELETE CASCADE
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_active_inquiries_status ON active_inquiries(status, updated_at DESC)")
        conn.commit()


def get_settings() -> dict:
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        row = conn.execute("SELECT * FROM active_inquiry_settings WHERE id=1").fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    return {
        "enabled": bool(row["enabled"]),
        "threshold": int(row["threshold"]),
        "max_rounds": int(row["max_rounds"]),
        "bargain_percent": float(row["bargain_percent"]),
        "prompt_file": row["prompt_file"],
        "account_state_file": row["account_state_file"] or "",
        "auto_send": bool(row["auto_send"]),
        "captcha_solver_enabled": bool(row["captcha_solver_enabled"]),
        "captcha_solver_endpoint": row["captcha_solver_endpoint"] or "",
        "captcha_solver_api_key": row["captcha_solver_api_key"] or "",
        "captcha_solver_pass_cookies": bool(row["captcha_solver_pass_cookies"]),
        "captcha_solver_timeout": int(row["captcha_solver_timeout"] or 60),
    }


def save_settings(payload: dict) -> dict:
    ensure_active_inquiry_schema()
    existing = get_settings()
    settings = merge_settings_payload(payload, existing)
    settings["threshold"] = max(0, min(100, int(settings.get("threshold") or 70)))
    settings["max_rounds"] = max(1, min(30, int(settings.get("max_rounds") or 6)))
    settings["bargain_percent"] = max(0, min(80, float(settings.get("bargain_percent") or 10)))
    settings["captcha_solver_timeout"] = max(20, min(120, int(settings.get("captcha_solver_timeout") or 60)))
    now = _now()
    with sqlite_connection() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO active_inquiry_settings
        (id, enabled, threshold, max_rounds, bargain_percent, prompt_file, account_state_file, auto_send,
         captcha_solver_enabled, captcha_solver_endpoint, captcha_solver_api_key, captcha_solver_pass_cookies,
         captcha_solver_timeout, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1 if settings["enabled"] else 0,
            settings["threshold"],
            settings["max_rounds"],
            settings["bargain_percent"],
            settings["prompt_file"],
            settings.get("account_state_file") or "",
            1 if settings.get("auto_send", True) else 0,
            1 if settings.get("captcha_solver_enabled") else 0,
            settings.get("captcha_solver_endpoint") or "",
            settings.get("captcha_solver_api_key") or "",
            1 if settings.get("captcha_solver_pass_cookies", True) else 0,
            settings["captcha_solver_timeout"],
            now,
        ))
        conn.commit()
    return public_settings(get_settings())


def _extract_seller_id(record: dict) -> str:
    seller = record.get("卖家信息", {}) or {}
    item = record.get("商品信息", {}) or {}
    for obj in (seller, item):
        for key in ("卖家ID", "seller_id", "sellerId", "user_id", "userId"):
            if obj.get(key):
                return str(obj.get(key))
    return ""


def _insert_message(inquiry_id: int, direction: str, role: str, content: str, raw: Any = None) -> None:
    with sqlite_connection() as conn:
        conn.execute("INSERT INTO active_inquiry_messages (inquiry_id, direction, role, content, raw_json, created_at) VALUES (?, ?, ?, ?, ?, ?)", (inquiry_id, direction, role, content, json.dumps(raw, ensure_ascii=False) if raw is not None else None, _now()))
        conn.commit()


def split_outbound_messages(text: str) -> list[str]:
    parts = [line.strip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return [part for part in parts if part]


def is_auto_reply_message(text: str) -> bool:
    value = re.sub(r"[\s，,。.！!？?～~（）()【】\[\]{}、；;：:]+", "", str(text or "")).lower()
    if not value:
        return False
    patterns = (
        "自动回复",
        "我现在不在线",
        "我现在不在",
        "当前不在线",
        "不在线商品还在",
        "不在喜欢可以拍下",
        "喜欢可以拍下有问题留言",
        "商品还在可以直接拍",
        "可以直接拍有问题请留言",
        "有问题请留言",
        "有问题留言",
        "会尽快回复",
    )
    return any(pattern.lower() in value for pattern in patterns)


def format_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or type(exc).__name__


def try_claim_inquiry_start(inquiry_id: int) -> bool:
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE active_inquiries
            SET status='starting', stage='starting', updated_at=?
            WHERE id=? AND status IN ('pending', 'failed')
            """,
            (_now(), inquiry_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def create_inquiry_from_record(
    record: dict,
    keyword: str,
    *,
    result_item_id: Optional[int] = None,
    ignore_enabled: bool = False,
    auto_start: Optional[bool] = None,
) -> Optional[int]:
    settings = get_settings()
    if not should_start_inquiry(record, settings, ignore_enabled=ignore_enabled):
        return None
    item = record.get("商品信息", {}) or {}
    seller = record.get("卖家信息", {}) or {}
    item_id = str(item.get("商品ID") or "")
    seller_id = _extract_seller_id(record)
    if not item_id or not seller_id:
        print(f"[主动咨询] 缺少 item_id/seller_id，跳过: item_id={item_id}, seller_id={seller_id}")
        return None
    price = _parse_price(item.get("当前售价"))
    target_price = round(price * (1 - float(settings["bargain_percent"]) / 100), 2) if price is not None else None
    score = extract_recommendation_score(record.get("ai_analysis", {}) or {})
    now = _now()
    with sqlite_connection() as conn:
        cursor = conn.execute("""
        INSERT OR IGNORE INTO active_inquiries
        (result_item_id, item_id, seller_id, seller_nickname, task_name, keyword, title, price, target_price, score, status, stage, chat_id, account_id, rounds, item_json, context_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'created', NULL, NULL, 0, ?, ?, ?, ?)
        """, (result_item_id, item_id, seller_id, seller.get("卖家昵称") or item.get("卖家昵称"), record.get("任务名称", ""), keyword, item.get("商品标题", ""), price, target_price, score, json.dumps(record, ensure_ascii=False), json.dumps({"settings": settings}, ensure_ascii=False), now, now))
        created = cursor.rowcount > 0
        row = conn.execute("SELECT id FROM active_inquiries WHERE item_id=? AND seller_id=?", (item_id, seller_id)).fetchone()
        conn.commit()
    inquiry_id = int(row["id"]) if row else None
    if inquiry_id:
        if created:
            print(f"[主动咨询] 已创建咨询 #{inquiry_id}: {item.get('商品标题', '')[:40]}")
        else:
            print(f"[主动咨询] 咨询已存在，跳过重复启动 #{inquiry_id}: {item.get('商品标题', '')[:40]}")
        should_auto_start = settings.get("auto_send", True) if auto_start is None else auto_start
        if created and should_auto_start:
            try:
                asyncio.get_running_loop()
                get_runtime().submit_start(inquiry_id)
            except RuntimeError:
                print(f"[主动咨询] 当前不在异步事件循环中，仅创建记录 #{inquiry_id}，等待前端手动启动")
    return inquiry_id


def create_inquiry_from_result_item(
    filename: str,
    item_id: str,
    *,
    auto_start: bool = True,
) -> Optional[int]:
    """Create an active inquiry from a historical result_items row."""
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        row = conn.execute(
            """
            SELECT id, keyword, raw_json
            FROM result_items
            WHERE result_filename = ? AND item_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (filename, item_id),
        ).fetchone()
    if row is None:
        raise ValueError("结果商品不存在")
    record = _json_loads(str(row["raw_json"]), {})
    if not isinstance(record, dict):
        raise ValueError("结果商品数据格式无效")
    return create_inquiry_from_record(
        record,
        str(row["keyword"] or record.get("搜索关键字") or ""),
        result_item_id=int(row["id"]),
        ignore_enabled=True,
        auto_start=auto_start,
    )


async def _call_ai_json(record: dict, messages: list[dict], settings: dict, stage: str) -> dict:
    prompt_path = Path(settings.get("prompt_file") or DEFAULT_PROMPT_FILE)
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else Path(DEFAULT_PROMPT_FILE).read_text(encoding="utf-8")
    user_payload = {
        "stage": stage,
        "商品信息": record.get("商品信息", {}),
        "卖家信息": record.get("卖家信息", {}),
        "价格参考": record.get("价格参考", {}),
        "AI分析": record.get("ai_analysis", {}),
        "砍价设置": {"target_price": record.get("_target_price"), "bargain_percent": settings.get("bargain_percent"), "max_rounds": settings.get("max_rounds")},
        "历史聊天": messages,
    }
    client = AIClient()
    try:
        text = await client._call_ai([
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ], temperature=0.4, max_output_tokens=1000, enable_json_output=True)
        data = _json_loads(text, {})
        if not isinstance(data, dict):
            data = {}
        return data
    finally:
        await client.close()


class ActiveInquiryRuntime:
    def __init__(self):
        self._clients: dict[str, ActiveInquiryImClient] = {}
        self._tasks: set[asyncio.Task] = set()
        self._replying: set[int] = set()

    def submit_start(self, inquiry_id: int) -> None:
        task = asyncio.create_task(self.start_inquiry(inquiry_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def get_client(self, account_state_file: str) -> ActiveInquiryImClient:
        state_path = account_state_file or _pick_first_state_file()
        if not state_path:
            raise RuntimeError("未配置主动咨询账号状态文件，且 state/ 下没有可用账号")
        if state_path in self._clients and self._clients[state_path].is_connected:
            return self._clients[state_path]
        snapshot = json.loads(Path(state_path).read_text(encoding="utf-8"))
        cookies_str = cookies_from_storage_state(snapshot)
        settings = get_settings()
        client = ActiveInquiryImClient(
            Path(state_path).stem,
            cookies_str,
            captcha_solver={
                "enabled": bool(settings.get("captcha_solver_enabled")),
                "endpoint": settings.get("captcha_solver_endpoint") or "",
                "api_key": settings.get("captcha_solver_api_key") or "",
                "pass_cookies": bool(settings.get("captcha_solver_pass_cookies", True)),
                "timeout": int(settings.get("captcha_solver_timeout") or 60),
            },
        )
        client.add_message_callback(self.on_message)
        await client.connect()
        self._clients[state_path] = client
        return client

    async def start_inquiry(self, inquiry_id: int) -> None:
        settings = get_settings()
        if not settings.get("enabled"):
            return
        inquiry = get_inquiry(inquiry_id)
        if not inquiry:
            return
        if inquiry["status"] not in {"pending", "failed"}:
            return
        if not try_claim_inquiry_start(inquiry_id):
            return
        inquiry = get_inquiry(inquiry_id)
        if not inquiry:
            return
        record = _json_loads(inquiry["item_json"], {})
        record["_target_price"] = inquiry["target_price"]
        try:
            client = await self.get_client(settings.get("account_state_file") or "")
            chat_id = await client.create_chat(inquiry["seller_id"], inquiry["item_id"])
            with sqlite_connection() as conn:
                conn.execute("UPDATE active_inquiries SET chat_id=?, account_id=?, status='running', stage='consulting', updated_at=? WHERE id=?", (chat_id, client.account_id, _now(), inquiry_id))
                conn.commit()
            ai = await _call_ai_json(record, [], settings, "initial")
            message = str(ai.get("message") or "").strip()
            if not message:
                message = "你好，我对这个商品挺感兴趣，想了解下成色和配件情况。"
            message_parts = split_outbound_messages(message)
            for part in message_parts:
                await client.send_text(chat_id, inquiry["seller_id"], part)
                _insert_message(inquiry_id, "out", "assistant", part, ai)
        except Exception as exc:
            with sqlite_connection() as conn:
                conn.execute("UPDATE active_inquiries SET status='failed', stage='error', updated_at=? WHERE id=?", (_now(), inquiry_id))
                conn.commit()
            _insert_message(inquiry_id, "system", "system", f"启动主动咨询失败: {format_exception_message(exc)}")

    async def on_message(self, msg: IncomingMessage) -> None:
        if msg.is_self or not msg.cid:
            return
        inquiry = find_running_by_chat(msg.cid)
        if not inquiry:
            return
        if is_auto_reply_message(msg.text):
            _insert_message(inquiry["id"], "system", "system", f"已忽略卖家自动回复: {msg.text}", msg.__dict__)
            return
        _insert_message(inquiry["id"], "in", "seller", msg.text, msg.__dict__)
        try:
            await self.reply_to_inquiry(int(inquiry["id"]))
        except Exception as exc:
            _insert_message(inquiry["id"], "system", "system", f"主动咨询回复失败: {format_exception_message(exc)}")

    async def reply_to_inquiry(self, inquiry_id: int) -> None:
        if inquiry_id in self._replying:
            return
        self._replying.add(inquiry_id)
        try:
            await self._reply_to_inquiry_locked(inquiry_id)
        finally:
            self._replying.discard(inquiry_id)

    async def _reply_to_inquiry_locked(self, inquiry_id: int) -> None:
        inquiry = get_inquiry(inquiry_id)
        if not inquiry or inquiry["status"] != "running":
            return
        settings = get_settings()
        messages = list_messages(inquiry_id)
        if int(inquiry["rounds"] or 0) >= int(settings.get("max_rounds", 6)):
            await finish_inquiry(inquiry_id, "已达到最大沟通轮数，等待管理员接管。")
            return
        record = _json_loads(inquiry["item_json"], {})
        record["_target_price"] = inquiry["target_price"]
        ai = await _call_ai_json(record, messages, settings, inquiry["stage"])
        if ai.get("stop"):
            await finish_inquiry(inquiry_id, ai.get("admin_summary") or "AI 判断咨询已完成。")
            return
        message = str(ai.get("message") or "").strip()
        if not message:
            return
        message_parts = split_outbound_messages(message)
        client = await self.get_client(settings.get("account_state_file") or "")
        for part in message_parts:
            await client.send_text(inquiry["chat_id"], inquiry["seller_id"], part)
            _insert_message(inquiry_id, "out", "assistant", part, ai)
        with sqlite_connection() as conn:
            conn.execute("UPDATE active_inquiries SET rounds=rounds+1, stage=?, updated_at=? WHERE id=?", (ai.get("stage") or inquiry["stage"], _now(), inquiry_id))
            conn.commit()


async def finish_inquiry(inquiry_id: int, summary: str) -> None:
    with sqlite_connection() as conn:
        conn.execute("UPDATE active_inquiries SET status='done', stage='done', updated_at=? WHERE id=?", (_now(), inquiry_id))
        conn.commit()
    _insert_message(inquiry_id, "system", "system", summary)
    try:
        inquiry = get_inquiry(inquiry_id)
        await send_ntfy_notification({"商品标题": f"[主动咨询完成] {inquiry['title']}", "当前售价": inquiry["price"], "商品链接": "#"}, summary)
    except Exception as exc:
        print(f"[主动咨询] 通知管理员失败: {exc}")


def _pick_first_state_file() -> str:
    for p in sorted(Path("state").glob("*.json")):
        return str(p)
    return ""


def get_runtime() -> ActiveInquiryRuntime:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = ActiveInquiryRuntime()
    return _RUNTIME


def get_inquiry(inquiry_id: int):
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        return conn.execute("SELECT * FROM active_inquiries WHERE id=?", (inquiry_id,)).fetchone()


def find_running_by_chat(chat_id: str):
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        return conn.execute("SELECT * FROM active_inquiries WHERE chat_id=? AND status='running'", (chat_id,)).fetchone()


def list_messages(inquiry_id: int) -> list[dict]:
    ensure_active_inquiry_schema()
    with sqlite_connection() as conn:
        rows = conn.execute("SELECT * FROM active_inquiry_messages WHERE inquiry_id=? ORDER BY id ASC", (inquiry_id,)).fetchall()
    return [dict(r) for r in rows]


def list_inquiries(status: str | None = None) -> list[dict]:
    ensure_active_inquiry_schema()
    sql = "SELECT * FROM active_inquiries"
    params: tuple = ()
    if status:
        sql += " WHERE status=?"
        params = (status,)
    sql += " ORDER BY updated_at DESC, id DESC LIMIT 200"
    with sqlite_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
