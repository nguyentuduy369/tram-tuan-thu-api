import os, json, httpx, re, asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

router = APIRouter()
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"
    department: str = ""

@router.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: return {"result": "Lỗi API"}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        system_instruction = f"""
        VAI TRÒ: "Chuyên Viên AI của Trạm Tuân Thủ" - Cố vấn B2B. PHÒNG BAN: [{req.department}]
        
        [LỆNH THÉP VỀ NGÔN NGỮ]: BẮT BUỘC nhận diện ngôn ngữ của khách.
        - NẾU KHÁCH GÕ TIẾNG ANH -> MÀY PHẢI TRẢ LỜI 100% TIẾNG ANH.
        - NẾU KHÁCH GÕ TIẾNG TRUNG -> TRẢ LỜI 100% TIẾNG TRUNG.
        
        KẾT THÚC BẮT BUỘC: Nguồn tham khảo: [...] — Chuyên Viên AI của Trạm Tuân Thủ.
        """
        payload = {"contents": [{"role": "user", "parts": [{"text": req.query}]}], "systemInstruction": {"parts": [{"text": system_instruction}]}, "tools": [{"googleSearch": {}}, {"retrieval": {"vertexAiSearch": {"datastore": "projects/679561966812/locations/global/collections/default_collection/dataStores/knowledge-compliance-hub_1772594714547"}}}]}
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}"}, timeout=60.0)
            return {"result": res.json()["candidates"][0]["content"]["parts"][0]["text"]}
    except Exception as e: return {"result": str(e)}

class TelemetryData(BaseModel):
    titles: list[str]; raw_info: str

@router.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"GUEST_{str(datetime.now().timestamp())[-4:]}"
        text = data.raw_info
        
        mst = re.search(r'\b\d{10}(?:-\d{3})?\b', text)
        zalo_phone = re.search(r'\b(0[3|5|7|8|9])+([0-9xX]{8})\b', text) # ĐÃ SỬA: Bắt được cả chữ X
        facebook = re.search(r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/[a-zA-Z0-9\.]+', text)
        tiktok = re.search(r'(?:https?:\/\/)?(?:www\.)?tiktok\.com\/@[a-zA-Z0-9\.\_]+', text)
        telegram = re.search(r'(?:https?:\/\/)?t\.me\/[a-zA-Z0-9\_]+', text)

        mst_str = mst.group(0) if mst else "Không"
        zalo_str = zalo_phone.group(0) if zalo_phone else "Không"
        fb_str = facebook.group(0) if facebook else "Không"
        tt_str = tiktok.group(0) if tiktok else "Không"
        tele_str = telegram.group(0) if telegram else "Không"

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            # ĐÃ SỬA: Trả lại nguyên trạng 3 tin nhắn mật
            msg1 = f"🟢 <b>[GHI CHÚ TRUY CẬP HỆ THỐNG]</b>\n⏱ {vn_time}\n👤 Định danh: {guest_id}\n🏢 Mã số DN: {mst_str}"
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg1, "parse_mode": "HTML"})
            await asyncio.sleep(0.5)

            if any(x != "Không" for x in [zalo_str, fb_str, tt_str, tele_str]):
                msg2 = f"📡 <b>[TUYẾN LIÊN KẾT NGOÀI]</b>\n📱 Mã Check-in (Z/P): {zalo_str}\n📘 Kênh Truyền thống: {fb_str}\n🎵 Luồng Giải trí: {tt_str}\n✈️ Tín hiệu Tốc độ cao: {tele_str}"
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg2, "parse_mode": "HTML"})
                await asyncio.sleep(0.5)

            safe_titles = [f"🔹 {re.sub(r'\\b\\d{11,16}\\b', '[ẨN_DẤU]', t[:45])}" for t in data.titles if t]
            if safe_titles:
                msg3 = f"📌 <b>[CHỈ MỤC QUAN TÂM]</b>\n{chr(10).join(safe_titles)}"
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg3, "parse_mode": "HTML"})
    except Exception: pass
    return {"status": "ok"}
