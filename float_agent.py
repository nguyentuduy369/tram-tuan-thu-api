import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

router = APIRouter()

# Két sắt: Tách biệt hoàn toàn, không mượn Token của Bot ẩn danh nữa
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
FLOAT_TELEGRAM_TOKEN = os.getenv("FLOAT_TELEGRAM_TOKEN", "") 
FLOAT_TELEGRAM_CHAT_ID = os.getenv("FLOAT_TELEGRAM_CHAT_ID", "")

class FloatRequest(BaseModel):
    query: str
    lang: str = "VN"
    user_name: str = "" 
    user_job: str = ""  

@router.post("/api/float-chat")
async def float_chat(req: FloatRequest):
    if not GCP_JSON_KEY: return {"result": "Hệ thống đang bảo trì..."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        # MASTER PROMPT V2: ĐA NGỮ & CHỐT SALE SẮC BÉN
        system_instruction = f"""
        VAI TRÒ: "Tiểu Khả Ái", nữ Cố vấn Chiến lược cấp cao của Trạm Tuân Thủ.
        KHÁCH HÀNG: Tên "{req.user_name}", Chức vụ "{req.user_job}". Xưng hô là "Tiểu Khả Ái" (hoặc "em") và gọi khách bằng [Chức vụ + Tên].
        
        CẢM BIẾN NGÔN NGỮ (TỐI QUAN TRỌNG): 
        - BẮT BUỘC tự động nhận diện ngôn ngữ trong câu hỏi của khách hàng.
        - Nếu khách hỏi bằng Tiếng Anh, PHẢI suy nghĩ và trả lời 100% bằng Tiếng Anh. Nếu là Tiếng Trung, trả lời Tiếng Trung.
        
        ĐỊNH DẠNG & TÂM LÝ CHỐT SALE (MINI-CHAT):
        - Ngắn gọn, súc tích (tối đa 3-4 câu).
        - Trả lời TRỰC DIỆN, đưa ra 1-2 thông tin có giá trị cao nhất. TUYỆT ĐỐI KHÔNG trả lời lấp lửng, cắt ngang câu hay dang dở.
        - Kết thúc LUÔN LUÔN bằng một câu hỏi gợi mở khéo léo để điều hướng khách hàng kết nối với chuyên gia (Ví dụ: "Vấn đề này còn nhiều góc khuất pháp lý, {req.user_name} có muốn em báo chuyên gia liên hệ riêng qua Zalo/Tele để bảo mật không?").
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [{"googleSearch": {}}] 
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}, timeout=60.0)
            text_reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            
            # GƯƠNG PHẢN CHIẾU: Chỉ bắn tin khi Token của nhóm Admin được cấu hình đúng
            if FLOAT_TELEGRAM_TOKEN and FLOAT_TELEGRAM_CHAT_ID:
                vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M")
                msg = (f"🌸 <b>[TIỂU KHẢ ÁI]</b>\n"
                       f"⏱ {vn_time}\n"
                       f"👤 Khách: <b>{req.user_job} {req.user_name}</b>\n"
                       f"💬 Hỏi: <i>{req.query[:150]}</i>\n"
                       f"🤖 Trả lời: {text_reply[:150]}...")
                await client.post(f"https://api.telegram.org/bot{FLOAT_TELEGRAM_TOKEN}/sendMessage", json={"chat_id": FLOAT_TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
            
            return {"result": text_reply}
    except Exception as e:
        return {"result": "Dạ em đang rà soát lại dữ liệu, anh/chị đợi em một chút nhé..."}
