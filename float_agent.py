import os, json, httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

router = APIRouter()
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
FLOAT_TELEGRAM_TOKEN = os.getenv("FLOAT_TELEGRAM_TOKEN", "") 
FLOAT_TELEGRAM_CHAT_ID = os.getenv("FLOAT_TELEGRAM_CHAT_ID", "")

class FloatRequest(BaseModel):
    query: str; lang: str = "VN"; user_name: str = ""; user_job: str = ""  

@router.post("/api/float-chat")
async def float_chat(req: FloatRequest):
    if not GCP_JSON_KEY: return {"result": "Hệ thống đang bảo trì..."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        system_instruction = f"""
        VAI TRÒ: "Tiểu Khả Ái", nữ Cố vấn B2B. KHÁCH HÀNG: "{req.user_name}", Chức vụ "{req.user_job}".
        
        [LỆNH THÉP VỀ NGÔN NGỮ]: 
        - NẾU KHÁCH GÕ TIẾNG ANH -> MÀY PHẢI TRẢ LỜI 100% BẰNG TIẾNG ANH.
        - NẾU KHÁCH GÕ TIẾNG TRUNG -> TRẢ LỜI 100% BẰNG TIẾNG TRUNG.
        - CẤM trả lời lấp lửng. Luôn kết thúc bằng một câu hỏi gợi mở hoặc đề xuất chat mật qua Zalo/Tele.
        """
        payload = {"contents": [{"role": "user", "parts": [{"text": req.query}]}], "systemInstruction": {"parts": [{"text": system_instruction}]}, "tools": [{"googleSearch": {}}]}
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}"}, timeout=60.0)
            text_reply = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            
            if FLOAT_TELEGRAM_TOKEN and FLOAT_TELEGRAM_CHAT_ID:
                vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M")
                msg = f"🌸 <b>[TIỂU KHẢ ÁI - ĐANG TƯ VẤN]</b>\n⏱ {vn_time}\n👤 Khách: <b>{req.user_job} {req.user_name}</b>\n\n💬 <b>Khách Hỏi:</b>\n{req.query}\n\n🤖 <b>Tiểu Khả Ái Trả lời:</b>\n{text_reply}"
                await client.post(f"https://api.telegram.org/bot{FLOAT_TELEGRAM_TOKEN}/sendMessage", json={"chat_id": FLOAT_TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
            
            return {"result": text_reply}
    except Exception as e: return {"result": "Dạ mạng hơi chập chờn, anh/chị đợi em một chút nhé..."}
