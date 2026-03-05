import os
import json
import httpx
from fastapi import APIRouter, BackgroundTasks

# Mở cửa riêng cho phòng Trinh Sát
router = APIRouter()

API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]

MASTER_PROMPT = """[ROLE] Bạn là Tổng biên tập Bản tin Doanh nghiệp B2B. 
[MISSION] Tạo 4 Hook (25-40 chữ) về chính sách, kinh tế 24h qua. 
[FORMAT] {"VN": ["✨ Hook 1",...], "EN": [...], "CN": [...]}"""

async def fetch_and_save_hooks_bg():
    if not API_KEYS: return
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[0]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}], "tools": [{"googleSearch": {}}]}
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f: 
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
        except Exception: pass

@router.get("/api/generate-hooks")
async def generate_hooks(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return {"status": "success"}

@router.get("/api/hooks")
async def get_hooks(background_tasks: BackgroundTasks):
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f: 
            return json.load(f)
    except FileNotFoundError:
        background_tasks.add_task(fetch_and_save_hooks_bg)
        return {
            "VN": ["✨ Đang tải tin tức pháp lý thời gian thực..."],
            "EN": ["✨ Loading real-time news..."],
            "CN": ["✨ 正在加载新闻..."]
        }
