from __future__ import annotations

import asyncio
import base64
import json
import random
import time
import hashlib
import struct
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import urlparse

import aiohttp


WS_URL = "wss://wss-goofish.dingtalk.com/"
TOKEN_API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"
APP_KEY = "34839810"
IM_APP_KEY = "444e9908a51d1cb236a27862abc769c9"


def trans_cookies(cookies_str: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in str(cookies_str or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key.strip():
            cookies[key.strip()] = value.strip()
    return cookies


def cookies_from_storage_state(snapshot: dict) -> str:
    cookies = snapshot.get("cookies") or []
    parts = []
    if isinstance(cookies, list):
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                parts.append(f"{name}={value}")
    return "; ".join(parts)


def generate_mid() -> str:
    return f"{int(1000 * random.random())}{int(time.time() * 1000)} 0"


def generate_uuid() -> str:
    return f"-{int(time.time() * 1000)}1"


def generate_device_id(user_id: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in [8, 13, 18, 23]:
            result.append("-")
        elif i == 14:
            result.append("4")
        elif i == 19:
            result.append(chars[(int(16 * random.random()) & 0x3) | 0x8])
        else:
            result.append(chars[int(16 * random.random())])
    return "".join(result) + "-" + user_id


def generate_sign(t: str, token: str, data: str) -> str:
    msg = f"{token}&{t}&{APP_KEY}&{data}"
    return hashlib.md5(msg.encode("utf-8")).hexdigest()


def _extract_response_cookies(headers: Any) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    getall = getattr(headers, "getall", None)
    values = getall("Set-Cookie", []) if callable(getall) else []
    for value in values:
        cookie = SimpleCookie()
        try:
            cookie.load(value)
        except Exception:
            continue
        for key, morsel in cookie.items():
            merged[key] = morsel.value
    return merged


class MessagePackDecoder:
    """MessagePack解码器的纯Python实现"""
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.length = len(data)
    
    def read_byte(self) -> int:
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")
        byte = self.data[self.pos]
        self.pos += 1
        return byte
    
    def read_bytes(self, count: int) -> bytes:
        if self.pos + count > self.length:
            raise ValueError("Unexpected end of data")
        result = self.data[self.pos:self.pos + count]
        self.pos += count
        return result
    
    def read_uint8(self) -> int:
        return self.read_byte()
    
    def read_uint16(self) -> int:
        return struct.unpack('>H', self.read_bytes(2))[0]
    
    def read_uint32(self) -> int:
        return struct.unpack('>I', self.read_bytes(4))[0]
    
    def read_uint64(self) -> int:
        return struct.unpack('>Q', self.read_bytes(8))[0]
    
    def read_int8(self) -> int:
        return struct.unpack('>b', self.read_bytes(1))[0]
    
    def read_int16(self) -> int:
        return struct.unpack('>h', self.read_bytes(2))[0]
    
    def read_int32(self) -> int:
        return struct.unpack('>i', self.read_bytes(4))[0]
    
    def read_int64(self) -> int:
        return struct.unpack('>q', self.read_bytes(8))[0]
    
    def read_float32(self) -> float:
        return struct.unpack('>f', self.read_bytes(4))[0]
    
    def read_float64(self) -> float:
        return struct.unpack('>d', self.read_bytes(8))[0]
    
    def read_string(self, length: int) -> str:
        return self.read_bytes(length).decode('utf-8')
    
    def decode_value(self) -> Any:
        """解码单个MessagePack值"""
        if self.pos >= self.length:
            raise ValueError("Unexpected end of data")
            
        format_byte = self.read_byte()
        
        # Positive fixint (0xxxxxxx)
        if format_byte <= 0x7f:
            return format_byte
        
        # Fixmap (1000xxxx)
        elif 0x80 <= format_byte <= 0x8f:
            size = format_byte & 0x0f
            return self.decode_map(size)
        
        # Fixarray (1001xxxx)
        elif 0x90 <= format_byte <= 0x9f:
            size = format_byte & 0x0f
            return self.decode_array(size)
        
        # Fixstr (101xxxxx)
        elif 0xa0 <= format_byte <= 0xbf:
            size = format_byte & 0x1f
            return self.read_string(size)
        
        # nil
        elif format_byte == 0xc0:
            return None
        
        # false
        elif format_byte == 0xc2:
            return False
        
        # true
        elif format_byte == 0xc3:
            return True
        
        # bin 8
        elif format_byte == 0xc4:
            size = self.read_uint8()
            return self.read_bytes(size)
        
        # bin 16
        elif format_byte == 0xc5:
            size = self.read_uint16()
            return self.read_bytes(size)
        
        # bin 32
        elif format_byte == 0xc6:
            size = self.read_uint32()
            return self.read_bytes(size)
        
        # float 32
        elif format_byte == 0xca:
            return self.read_float32()
        
        # float 64
        elif format_byte == 0xcb:
            return self.read_float64()
        
        # uint 8
        elif format_byte == 0xcc:
            return self.read_uint8()
        
        # uint 16
        elif format_byte == 0xcd:
            return self.read_uint16()
        
        # uint 32
        elif format_byte == 0xce:
            return self.read_uint32()
        
        # uint 64
        elif format_byte == 0xcf:
            return self.read_uint64()
        
        # int 8
        elif format_byte == 0xd0:
            return self.read_int8()
        
        # int 16
        elif format_byte == 0xd1:
            return self.read_int16()
        
        # int 32
        elif format_byte == 0xd2:
            return self.read_int32()
        
        # int 64
        elif format_byte == 0xd3:
            return self.read_int64()
        
        # str 8
        elif format_byte == 0xd9:
            size = self.read_uint8()
            return self.read_string(size)
        
        # str 16
        elif format_byte == 0xda:
            size = self.read_uint16()
            return self.read_string(size)
        
        # str 32
        elif format_byte == 0xdb:
            size = self.read_uint32()
            return self.read_string(size)
        
        # array 16
        elif format_byte == 0xdc:
            size = self.read_uint16()
            return self.decode_array(size)
        
        # array 32
        elif format_byte == 0xdd:
            size = self.read_uint32()
            return self.decode_array(size)
        
        # map 16
        elif format_byte == 0xde:
            size = self.read_uint16()
            return self.decode_map(size)
        
        # map 32
        elif format_byte == 0xdf:
            size = self.read_uint32()
            return self.decode_map(size)
        
        # Negative fixint (111xxxxx)
        elif format_byte >= 0xe0:
            return format_byte - 0x100
        
        raise ValueError(f"Unknown format byte: {format_byte:02x}")

    def decode_array(self, size: int) -> List[Any]:
        """解码数组"""
        return [self.decode_value() for _ in range(size)]

    def decode_map(self, size: int) -> Dict[Any, Any]:
        """解码字典"""
        result = {}
        for _ in range(size):
            key = self.decode_value()
            value = self.decode_value()
            result[key] = value
        return result

    def decode(self) -> Any:
        """解码整个MessagePack数据"""
        return self.decode_value()


def decrypt(data: str) -> str:
    """解密消息数据
    
    Args:
        data: Base64编码的MessagePack数据
        
    Returns:
        解密后的JSON字符串
        
    Raises:
        Exception: 解密失败时抛出异常
    """
    try:
        if not isinstance(data, str):
            data = str(data)

        # 清理数据
        try:
            data.encode('ascii')
        except UnicodeEncodeError:
            data = data.encode('utf-8', errors='ignore').decode('ascii', errors='ignore')

        # Base64解码
        try:
            decoded_data = base64.b64decode(data)
        except Exception:
            missing_padding = len(data) % 4
            if missing_padding:
                data += '=' * (4 - missing_padding)
            decoded_data = base64.b64decode(data)

        # MessagePack解码
        decoder = MessagePackDecoder(decoded_data)
        decoded_value = decoder.decode()

        # 转换为JSON字符串
        if isinstance(decoded_value, dict):
            def json_serializer(obj):
                if isinstance(obj, bytes):
                    return obj.decode('utf-8', errors='ignore')
                raise TypeError(f"Type {type(obj)} not serializable")

            return json.dumps(decoded_value, default=json_serializer, ensure_ascii=False)

        return str(decoded_value)

    except Exception as e:
        raise Exception(f"解密失败: {str(e)}")


@dataclass
class IncomingMessage:
    cid: str
    sender_id: str
    sender_name: str
    text: str
    is_self: bool
    item_id: str = ""
    message_id: str = ""


class ActiveInquiryImClient:
    """Minimal Goofish IM client for buyer-side active inquiries."""

    def __init__(self, account_id: str, cookies_str: str, captcha_solver: Optional[dict] = None):
        self.account_id = account_id
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str)
        self.myid = self.cookies.get("unb") or self.cookies.get("munb") or ""
        if not self.myid:
            raise ValueError("Cookie 缺少 unb/munb，无法连接闲鱼 IM")
        self.device_id = generate_device_id(self.myid)
        self.captcha_solver = captcha_solver or {}
        self.token = ""
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._pending: dict[str, asyncio.Future] = {}
        self._recv_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable[[IncomingMessage], Awaitable[None]]] = []
        self.last_token_error = ""

    @property
    def is_connected(self) -> bool:
        recv_alive = bool(self._recv_task and not self._recv_task.done())
        return bool(self._ws and not self._ws.closed and self._session and not self._session.closed and recv_alive)

    def add_message_callback(self, callback: Callable[[IncomingMessage], Awaitable[None]]) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    async def connect(self) -> None:
        if self.is_connected:
            return
        self.token = await self._fetch_token()
        if not self.token:
            reason = self.last_token_error or "获取闲鱼 IM token 失败"
            raise RuntimeError(reason)
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            WS_URL,
            headers={
                "Cookie": self.cookies_str,
                "Origin": "https://www.goofish.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
            heartbeat=30,
            timeout=aiohttp.ClientTimeout(total=None, connect=30, sock_connect=30, sock_read=None),
        )
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self._register()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def close(self) -> None:
        for task in (self._heartbeat_task, self._recv_task):
            if task and not task.done():
                task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    async def force_close(self) -> None:
        await self.close()

    async def _solve_captcha(self, verify_url: str) -> bool:
        cfg = self.captcha_solver or {}
        if not (cfg.get("enabled") and cfg.get("endpoint") and cfg.get("api_key")):
            self.last_token_error = "闲鱼触发风控滑块验证，但未配置外部滑块解决服务"
            return False
        parsed = urlparse(verify_url)
        host = (parsed.hostname or "").lower()
        if not host or (host != "goofish.com" and not host.endswith(".goofish.com")):
            self.last_token_error = "闲鱼滑块验证链接主机异常，已拒绝调用外部服务"
            return False
        payload = {
            "secret_key": str(cfg.get("api_key") or ""),
            "account_id": self.account_id,
            "url": verify_url,
            "browser_timeout": int(cfg.get("timeout") or 60),
        }
        if cfg.get("pass_cookies", True):
            payload["cookies"] = self.cookies_str
            payload["device_id"] = self.device_id
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    str(cfg["endpoint"]),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=max(30, int(cfg.get("timeout") or 60) + 20)),
                ) as resp:
                    result = await resp.json(content_type=None)
        except Exception as exc:
            self.last_token_error = f"外部滑块服务调用失败: {type(exc).__name__}"
            return False
        if not (isinstance(result, dict) and result.get("success")):
            message = str(result.get("message") or "过滑块失败") if isinstance(result, dict) else "过滑块失败"
            self.last_token_error = f"外部滑块服务未通过: {message[:120]}"
            return False
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        cookies = data.get("cookies") if isinstance(data.get("cookies"), dict) else {}
        if not cookies:
            self.last_token_error = "外部滑块服务成功但未返回 cookies"
            return False
        self.cookies.update({str(k): str(v) for k, v in cookies.items() if str(k)})
        self.cookies_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        return True

    async def _fetch_token(self) -> str:
        timestamp = str(int(time.time() * 1000))
        data_val = json.dumps({"appKey": IM_APP_KEY, "deviceId": self.device_id}, separators=(",", ":"))
        token_part = self.cookies.get("_m_h5_tk", "").split("_")[0]
        sign = generate_sign(timestamp, token_part, data_val)
        params = {
            "jsv": "2.7.2",
            "appKey": APP_KEY,
            "t": timestamp,
            "sign": sign,
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idlemessage.pc.login.token",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.im.0.0",
            "spm_pre": "a21ybx.home.sidebar.1.4c053da6vYwnmf",
            "log_id": "4c053da6vYwnmf",
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": self.cookies_str,
            "referer": "https://www.goofish.com/",
            "origin": "https://www.goofish.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
        }
        async with aiohttp.ClientSession() as session:
            for attempt in range(4):
                if attempt:
                    timestamp = str(int(time.time() * 1000))
                    token_part = self.cookies.get("_m_h5_tk", "").split("_")[0]
                    params["t"] = timestamp
                    params["sign"] = generate_sign(timestamp, token_part, data_val)
                    headers["cookie"] = self.cookies_str
                async with session.post(TOKEN_API_URL, params=params, data={"data": data_val}, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    result = await resp.json(content_type=None)
                    new_cookies = _extract_response_cookies(resp.headers)
                    if new_cookies:
                        self.cookies.update(new_cookies)
                        self.cookies_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
                ret_text = str(result.get("ret", []))
                token = str((result.get("data") or {}).get("accessToken") or "")
                if token:
                    self.last_token_error = ""
                    return token
                data = result.get("data") if isinstance(result.get("data"), dict) else {}
                verify_url = str(data.get("url") or "")
                if "FAIL_SYS_USER_VALIDATE" in ret_text or "punish" in verify_url or "被挤爆" in ret_text:
                    if attempt >= 2 or not await self._solve_captcha(verify_url):
                        if not self.last_token_error:
                            self.last_token_error = "闲鱼触发风控滑块验证，外部滑块服务未能解除风控"
                        return ""
                    continue
                if "令牌过期" not in ret_text:
                    self.last_token_error = f"获取闲鱼 IM token 失败: {ret_text[:120]}"
                    return ""
        self.last_token_error = "获取闲鱼 IM token 失败: 令牌过期重试后仍无 accessToken"
        return ""

    async def _register(self) -> None:
        reg_mid = generate_mid()
        await self._send_and_wait(reg_mid, {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": IM_APP_KEY,
                "token": self.token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/146.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": reg_mid,
            },
        }, timeout=8)
        current_time = int(time.time() * 1000)
        await self._send_raw({
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [{"pipeline": "sync", "tooLong2Tag": "PNM,1", "channel": "sync", "topic": "sync", "highPts": 0, "pts": current_time * 1000, "seq": 0, "timestamp": current_time}],
        })
        await asyncio.sleep(1)

    async def create_chat(self, to_user_id: str, item_id: str) -> str:
        await self.connect()
        mid = generate_mid()
        response = await self._send_and_wait(mid, {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {"mid": mid},
            "body": [{
                "pairFirst": f"{to_user_id}@goofish",
                "pairSecond": f"{self.myid}@goofish",
                "bizType": "1",
                "extension": {"itemId": str(item_id)},
                "ctx": {"appVersion": "1.0", "platform": "web"},
            }],
        }, timeout=15)
        cid = self._extract_cid(response)
        if not cid:
            raise RuntimeError(f"创建会话响应中未找到 cid: {json.dumps(response, ensure_ascii=False)[:300]}")
        return cid

    async def send_text(self, cid: str, to_user_id: str, text: str) -> dict:
        await self.connect()
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"
        full_to = to_user_id if "@goofish" in to_user_id else f"{to_user_id}@goofish"
        payload = {"contentType": 1, "text": {"text": text}}
        data_b64 = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        mid = generate_mid()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [{
                "uuid": generate_uuid(),
                "cid": full_cid,
                "conversationType": 1,
                "content": {"contentType": 101, "custom": {"type": 1, "data": data_b64}},
                "redPointPolicy": 0,
                "extension": {"extJson": "{}"},
                "ctx": {"appVersion": "1.0", "platform": "web"},
                "mtags": {},
                "msgReadStatusSetting": 1,
            }, {"actualReceivers": [full_to, f"{self.myid}@goofish"]}],
        }
        response = await self._send_and_wait(mid, msg)
        body = response.get("body", {})
        if isinstance(body, dict) and body.get("reason"):
            raise RuntimeError(body.get("reason"))
        return response

    async def _send_raw(self, msg: dict) -> None:
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket未连接")
        await self._ws.send_json(msg)

    async def _send_and_wait(self, mid: str, msg: dict, timeout: float = 45) -> dict:
        if not self._ws or self._ws.closed:
            raise RuntimeError("WebSocket未连接")
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending[mid] = fut
        try:
            await self._ws.send_json(msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(mid, None)

    async def _recv_loop(self) -> None:
        try:
            async for ws_msg in self._ws:
                if ws_msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_ws_text(ws_msg.data)
                elif ws_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[主动咨询] IM接收异常: {exc}")

    async def _handle_ws_text(self, data: str) -> None:
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return
        headers = message.get("headers", {}) or {}
        mid = headers.get("mid", generate_mid())
        ack = {"code": 200, "headers": {"mid": mid, "sid": headers.get("sid", "")}}
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]
        try:
            await self._send_raw(ack)
        except Exception:
            pass
        if mid in self._pending:
            fut = self._pending[mid]
            if not fut.done():
                fut.set_result(message)
            return
        incoming_messages = self._parse_pushes(message)
        for incoming in incoming_messages:
            for cb in list(self._callbacks):
                await cb(incoming)

    def _parse_pushes(self, message: dict) -> list[IncomingMessage]:
        body = message.get("body", {})
        sync_pkg = body.get("syncPushPackage") if isinstance(body, dict) else None
        if not sync_pkg:
            return []
        parsed_messages: list[IncomingMessage] = []
        data_list = sync_pkg.get("data") or []
        for sync_data in data_list:
            raw = sync_data.get("data") if isinstance(sync_data, dict) else None
            decoded = self._decode_push_data(raw)
            if not isinstance(decoded, dict):
                continue
            parsed = self._parse_decoded_message(decoded)
            if parsed:
                parsed_messages.append(parsed)
        return parsed_messages

    def _parse_push(self, message: dict) -> Optional[IncomingMessage]:
        messages = self._parse_pushes(message)
        return messages[0] if messages else None

    def _decode_push_data(self, data: str | None) -> Optional[dict]:
        if not data:
            return None
        try:
            decoded = base64.b64decode(data).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            try:
                return json.loads(decrypt(data))
            except Exception:
                return None

    def _parse_decoded_message(self, msg: dict) -> Optional[IncomingMessage]:
        msg_1 = msg.get("1")
        if not isinstance(msg_1, dict):
            return None
        msg_10 = msg_1.get("10") or {}
        if not isinstance(msg_10, dict) or msg_10.get("reminderContent") is None:
            return None
        sender_id = str(msg_10.get("senderUserId") or "").split("@")[0]
        cid = str(msg_1.get("2") or "").split("@")[0]
        text = str(msg_10.get("reminderContent") or "")
        item_id = ""
        for source in (msg_10.get("reminderUrl"), msg_10.get("bizTag"), msg_10.get("extJson")):
            if not source:
                continue
            try:
                if "itemId=" in str(source):
                    item_id = str(source).split("itemId=", 1)[1].split("&", 1)[0]
                    break
                data = json.loads(source) if isinstance(source, str) else source
                if isinstance(data, dict) and data.get("itemId"):
                    item_id = str(data.get("itemId"))
                    break
            except Exception:
                pass
        return IncomingMessage(
            cid=cid,
            sender_id=sender_id,
            sender_name=str(msg_10.get("senderNick") or msg_10.get("reminderTitle") or ""),
            text=text,
            is_self=sender_id == self.myid,
            item_id=item_id,
            message_id=str(msg_1.get("3") or ""),
        )

    @staticmethod
    def _extract_cid(response: dict) -> Optional[str]:
        body = response.get("body")
        first = body[0] if isinstance(body, list) and body and isinstance(body[0], dict) else body if isinstance(body, dict) else None
        if not isinstance(first, dict):
            return None
        candidates = [
            first.get("singleChatConversation"),
            ((first.get("singleChatUserConversation") or {}).get("singleChatConversation") if isinstance(first.get("singleChatUserConversation"), dict) else None),
            ((first.get("data") or {}).get("singleChatConversation") if isinstance(first.get("data"), dict) else None),
            first,
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                cid = candidate.get("cid") or candidate.get("id")
                if isinstance(cid, str) and cid:
                    return cid.split("@", 1)[0]
        return None

    async def _heartbeat_loop(self) -> None:
        try:
            while self.is_connected:
                await asyncio.sleep(15)
                if self.is_connected:
                    await self._send_raw({"lwp": "/!", "headers": {"mid": generate_mid()}})
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[主动咨询] 心跳异常: {exc}")
