import os
import json
import httpx
from fastapi import APIRouter, BackgroundTasks

router = APIRouter()
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]

MASTER_PROMPT = """[ROLE] Bạn là Copywriter B2B đỉnh cao.
[MISSION] Tạo 4 câu Hook thu hút về kinh tế luật pháp doanh nghiệp thuế hoặc quản trị SME.
[RULES] 
BẮT BUỘC mỗi Hook phải có độ dài TỐI THIỂU 25 CHỮ và TỐI ĐA 40 CHỮ.
Phải là một câu hoàn chỉnh cung cấp thông tin hữu ích nhưng giấu lại điểm mấu chốt để gây tò mò.
[FORMAT] {"VN": ["Hook 1...", "Hook 2..."], "EN": ["..."], "CN": ["..."]}"""

memory_hooks = {
    "VN": ["Thuế siết chặt kiểm tra hóa đơn điện tử 2026 rủi ro tiềm ẩn cho doanh nghiệp", "Lãi suất vay B2B giảm cơ hội mở rộng vốn kinh doanh hiệu quả", "Quy định BHXH mới ảnh hưởng trực tiếp quỹ lương cần lưu ý ngay", "5 rủi ro pháp lý SME thường gặp khi ký hợp đồng thương mại"],
    "EN": ["Tax authorities tighten e-invoice inspections hidden risks for enterprises", "B2B loan interest rates show signs of cooling expansion opportunity", "New social insurance rules affect payroll funds take note immediately", "Top 5 legal risks for SMEs when signing commercial contracts"],
    "CN": ["税务机关加强电子发票检查企业隐藏风险", "B2B贷款利率出现降温迹象扩张机会", "新的社保规定直接影响工资基金请立即注意", "中小企业签订商业合同时面临的五大法律风险"]
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
