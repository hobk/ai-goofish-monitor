from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.services.active_inquiry_service import (
    ensure_active_inquiry_schema,
    get_settings,
    save_settings,
    list_inquiries,
    list_messages,
    get_runtime,
    get_inquiry,
    finish_inquiry,
)

router = APIRouter(prefix="/api/active-inquiry", tags=["active-inquiry"])


class ActiveInquirySettingsPayload(BaseModel):
    enabled: bool = False
    threshold: int = Field(70, ge=0, le=100)
    max_rounds: int = Field(6, ge=1, le=30)
    bargain_percent: float = Field(10, ge=0, le=80)
    prompt_file: str = "prompts/active_inquiry_prompt.txt"
    account_state_file: str = ""
    auto_send: bool = True


@router.get("/settings")
async def read_active_inquiry_settings():
    ensure_active_inquiry_schema()
    return get_settings()


@router.put("/settings")
async def update_active_inquiry_settings(payload: ActiveInquirySettingsPayload):
    return save_settings(payload.model_dump())


@router.get("/inquiries")
async def read_active_inquiries(status: Optional[str] = Query(None)):
    return {"items": list_inquiries(status=status)}


@router.get("/inquiries/{inquiry_id}")
async def read_active_inquiry_detail(inquiry_id: int):
    inquiry = get_inquiry(inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="主动咨询不存在")
    return {"inquiry": dict(inquiry), "messages": list_messages(inquiry_id)}


@router.post("/inquiries/{inquiry_id}/start")
async def start_active_inquiry(inquiry_id: int):
    inquiry = get_inquiry(inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="主动咨询不存在")
    get_runtime().submit_start(inquiry_id)
    return {"message": "已提交启动"}


@router.post("/inquiries/{inquiry_id}/stop")
async def stop_active_inquiry(inquiry_id: int):
    inquiry = get_inquiry(inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="主动咨询不存在")
    await finish_inquiry(inquiry_id, "管理员手动停止主动咨询。")
    return {"message": "已停止"}
