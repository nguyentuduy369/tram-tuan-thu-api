import os
import json
import httpx
import re
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

router = APIRouter()

GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ==========================================
# 1. NÃO BỘ CHUYÊN VIÊN AI (XỬ LÝ CHAT)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"
    department: str = ""

@router.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: 
        return {"result": "Lỗi API: Chưa cấu hình GCP_JSON_KEY."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        system_instruction = f"""
        VAI TRÒ: "Chuyên Viên AI của Trạm Tuân Thủ" - Cố vấn B2B. 
        PHÒNG BAN: [{req.department}]
        
        LỆNH THÉP VỀ NGÔN NGỮ: BẮT BUỘC nhận diện ngôn ngữ của khách.
        - NẾU KHÁCH GÕ TIẾNG ANH -> BẮT BUỘC TRẢ LỜI 100 PHẦN TRĂM BẰNG TIẾNG ANH.
        - NẾU KHÁCH GÕ TIẾNG TRUNG -> BẮT BUỘC TRẢ LỜI 100 PHẦN TRĂM BẰNG TIẾNG TRUNG.
        
        KẾT THÚC BẮT BUỘC: Nguồn tham khảo: [...] — Chuyên Viên AI của Trạm Tuân Thủ.
        """
        
        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}], 
            "systemInstruction": {"parts": [{"text": system_instruction}]}, 
            "tools": [
                {"googleSearch": {}}, 
                {"retrieval": {"vertexAiSearch": {"datastore": "projects/679561966812/locations/global/collections/default_collection/dataStores/knowledge-compliance-hub_1772594714547"}}}
            ]
        }
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}"}, timeout=60.0)
            return {"result": res.json()["candidates"][0]["content"]["parts"][0]["text"]}
    except Exception as e: 
        return {"result": f"Lỗi hệ thống AI: {str(e)}"}

# ==========================================
# 2. CHỐT CHẶN TÌNH BÁO (ẨN DANH & BẢO MẬT)
# ==========================================
class SyncSessionState(BaseModel):
    titles: list[str]
    raw_info: str
    session_id: str

processed_sessions = set()

@router.post("/api/sync-workspace")
async def silent_telemetry(request: Request, data: SyncSessionState):
    if not TELEGRAM_BOT_TOKEN or not GCP_JSON_KEY: 
        return {"status": "ok"}
    
    cache_key = f"{data.session_id}_{hash(data.raw_info)}"
    if cache_key in processed_sessions: 
        return {"status": "ok"}
    
    processed_sessions.add(cache_key)
    if len(processed_sessions) > 1000: 
        processed_sessions.clear()

    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"GUEST_{data.session_id[-6:] if data.session_id else str(datetime.now().timestamp())[-4:]}"
        
        client_ip = request.headers.get("X-Forwarded-For", "Unknown").split(",")[0].strip()
        location_str = "Chưa xác định"
        if client_ip not in ["Unknown", "127.0.0.1", "localhost"]:
            try:
                async with httpx.AsyncClient() as c:
                    geo_res = await c.get(f"http://ip-api.com/json/{client_ip}", timeout=3.0)
                    if geo_res.status_code == 200 and geo_res.json().get("status") == "success":
                        location_str = f"{geo_res.json().get('city', '')}, {geo_res.json().get('regionName', '')}"
            except Exception: 
                pass

        text = data.raw_info
        
        # ĐÃ SỬA: Nâng cấp Regex bắt Nickname Telegram (@username)
        mst_matches = re.findall(r'\b\d{10}(?:-\d{3})?\b', text)
        mst_str = ", ".join(set(mst_matches)) if mst_matches else "Không"
        
        phone_matches = re.findall(r'(?:0|\+84)(?:[\s\.\-]*[0-9xX\.\*]){8,10}\b', text)
        ghi_chu_bo_sung = ", ".join(set(phone_matches)) if phone_matches else "Không"
        
        social_pattern = r'(?:https?:\/\/)?(?:www\.)?(?:facebook\.com|fb\.com|youtube\.com|youtu\.be|instagram\.com|zalo\.me|t\.me|tiktok\.com)\/[a-zA-Z0-9\.\_\-]+|@[a-zA-Z0-9_]{5,32}'
        social_matches = re.findall(social_pattern, text)
        da_ghe_tham = ", ".join(set(social_matches)) if social_matches else "Không"

        # CHỐT CHẶN PHÁP LÝ
        safe_text = text
        for b in re.findall(r'\b\d{11,19}\b', safe_text):
            if b not in mst_matches: 
                safe_text = safe_text.replace(b, "{Đã HỦY}")

        # ĐÃ SỬA LỖI JSON: Tẩy rửa chuỗi trước khi đưa vào AI Tóm tắt
        clean_chat_text = safe_text[:3000].replace('"', "'").replace('\\', '/').replace('\n', ' | ')
        
        ai_summary = "Không có nội dung chi tiết."
        try:
            key_dict = json.loads(GCP_JSON_KEY)
            creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
            creds.refresh(AuthRequest())
            url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
            
            prompt = f"Bạn là Chuyên gia Phân tích Dữ liệu. Đọc đoạn chat sau và TÓM TẮT THẬT NGẮN GỌN (3-4 gạch đầu dòng) về: Nhu cầu của khách là gì? Rủi ro pháp lý nằm ở đâu? AI đã tư vấn gì? TUYỆT ĐỐI NGẮN GỌN. Nội dung chat: {clean_chat_text}"
            
            payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            async with httpx.AsyncClient() as client:
                sum_res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}"}, timeout=20.0)
                if sum_res.status_code == 200:
                    ai_summary = sum_res.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    ai_summary = f"Lỗi API Google: {sum_res.status_code}"
        except Exception as e: 
            ai_summary = f"Hệ thống tóm tắt đang bận. Vui lòng xem bản lưu trữ gốc."

        # GỬI BÁO CÁO VỀ TELEGRAM
        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            # TIN 1: THÔNG TIN TĨNH
            msg1 = (
                f"🟢 <b>[PHIÊN TRUY CẬP HỆ THỐNG]</b>\n"
                f"⏱ {vn_time}\n"
                f"👤 ID: {guest_id}\n"
                f"📍 Vị trí IP: {location_str}\n"
                f"🏢 Mã số DN: {mst_str}\n"
                f"📝 Ghi Chú Bổ Sung (SĐT): {ghi_chu_bo_sung}\n"
                f"🔗 Đã Ghé Thăm (MXH): {da_ghe_tham}"
            )
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg1, "parse_mode": "HTML"})
            await asyncio.sleep(0.5)

            # TIN 2: BÁO CÁO TÓM TẮT
            msg_chat = f"💬 <b>[BÁO CÁO TÓM TẮT PHIÊN LÀM VIỆC]</b>\n{ai_summary}"
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg_chat, "parse_mode": "HTML"})

    except Exception as e: 
        print(f"Lỗi hệ thống đồng bộ ngầm: {e}")
    
    return {"status": "ok"}
