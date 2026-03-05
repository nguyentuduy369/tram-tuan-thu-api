import os
import json
import httpx
from fastapi import APIRouter, BackgroundTasks

router = APIRouter()
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]

MASTER_PROMPT = """[ROLE] Bạn là Tổng biên tập Bản tin Doanh nghiệp B2B. 
[MISSION] Tạo 4 Hook (25-40 chữ) về chính sách, kinh tế. 
[FORMAT] {"VN": ["✨ Hook 1",...], "EN": [...], "CN": [...]}"""

# ĐÃ SỬA: Lưu Hook vào RAM. Mở web là có ngay, không phụ thuộc file JSON!
memory_hooks = {
    "VN": ["✨ Thuế siết chặt kiểm tra hóa đơn điện tử 2026...", "✨ Lãi suất vay B2B giảm, cơ hội mở rộng vốn...", "✨ Quy định BHXH mới ảnh hưởng trực tiếp quỹ lương...", "✨ 5 rủi ro pháp lý SME thường gặp khi ký hợp đồng..."],
    "EN": ["✨ Tax authorities tighten e-invoice inspections...", "✨ B2B loan interest rates show signs of cooling...", "✨ New social insurance rules affect payroll...", "✨ Top 5 legal risks for SMEs..."],
    "CN": ["✨ 税务机关加强电子发票检查...", "✨ B2B贷款利率出现降温迹象...", "✨ 新的社保规定影响工资基金...", "✨ 中小企业面临的五大法律风险..."]
}

async def fetch_and_save_hooks_bg():
    global memory_hooks
    if not API_KEYS: return
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[0]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}]}
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                clean_json = response.json()["candidates"][0]["content"]["parts"][0]["text"].replace("```json", "").replace("```", "").strip()
                memory_hooks = json.loads(clean_json)
        except Exception: pass

@router.get("/api/generate-hooks")
async def generate_hooks(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return {"status": "success"}

@router.get("/api/hooks")
async def get_hooks(background_tasks: BackgroundTasks):
    global memory_hooks
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return memory_hooks
