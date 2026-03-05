import os
import json
import httpx
import re
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

# Mở cửa riêng cho phòng Chuyên viên
router = APIRouter()

# Két sắt
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- NÃO BỘ CHUYÊN VIÊN AI ---
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"
    department: str = ""

@router.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: return {"result": "Lỗi: Chưa cấu hình GCP_JSON_KEY."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        system_instruction = f"""
        VAI TRÒ TỐI CAO: "Chuyên Viên AI của Trạm Tuân Thủ" - Cấp bậc Cố vấn B2B.
        PHÒNG BAN CHUYÊN TRÁCH: [{req.department if req.department else "Tổng hợp Đa ngành"}]
        YÊU CẦU: Phân tích vấn đề bằng thuật ngữ chuyên ngành {req.department}. Trả lời bằng {req.lang}. Ưu tiên tìm trong 'vertexAiSearch'.
        KẾT THÚC BẮT BUỘC: Nguồn tham khảo: [...] — Chuyên Viên AI của Trạm Tuân Thủ.
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [{"googleSearch": {}}, {"retrieval": {"vertexAiSearch": {"datastore": "projects/679561966812/locations/global/collections/default_collection/dataStores/knowledge-compliance-hub_1772594714547"}}}]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}, timeout=60.0)
            if response.status_code == 200:
                return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
            else:
                return {"result": f"Lỗi truy xuất Kho Dữ Liệu: {response.status_code}"}
    except Exception as e:
        return {"result": f"Lỗi kết nối máy chủ: {str(e)}"}

# --- LƯỚI TÌNH BÁO BÓNG MA ---
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@router.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        guest_id = f"GUEST_{str(datetime.now().timestamp())[-4:]}"
        text = data.raw_info
        
        mst = re.search(r'\b\d{10}(?:-\d{3})?\b', text)
        zalo = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text)
        
        mst_str = mst.group(0) if mst else "Không"
        zalo_str = zalo.group(0) if zalo else "Không"

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            # Tin 1
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🟢 <b>[GHI CHÚ TRUY CẬP]</b>\n⏱ {vn_time}\n👤 {guest_id}\n🏢 Mã số DN: {mst_str}", "parse_mode": "HTML"})
            await asyncio.sleep(0.5)
            
            # Tin 2 (Nếu có SĐT)
            if zalo_str != "Không":
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"📡 <b>[TUYẾN LIÊN KẾT NGOÀI]</b>\n📱 Zalo/Phone: {zalo_str}", "parse_mode": "HTML"})
                await asyncio.sleep(0.5)
                
            # Tin 3
            safe_titles = [f"🔹 {t[:45]}" for t in data.titles if t]
            if safe_titles:
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": f"📌 <b>[CHỈ MỤC QUAN TÂM]</b>\n{chr(10).join(safe_titles)}", "parse_mode": "HTML"})
                
    except Exception: pass
    return {"status": "ok"}
