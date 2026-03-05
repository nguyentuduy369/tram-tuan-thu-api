import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

# Khởi tạo Cửa riêng cho phòng này
router = APIRouter()

# Két sắt nội bộ của phòng
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
FLOAT_TELEGRAM_TOKEN = os.getenv("FLOAT_TELEGRAM_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
FLOAT_TELEGRAM_CHAT_ID = os.getenv("FLOAT_TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))

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
        
        # BỘ MASTER PROMPT MỚI: SÁT THỦ CHỐT SALE & BẬC THẦY TÂM LÝ
        system_instruction = f"""
        VAI TRÒ: Bạn là "Tiểu Khả Ái", nữ Cố vấn Chiến lược cấp cao mang vỏ bọc trợ lý dễ thương của Trạm Tuân Thủ.
        KHÁCH HÀNG: Tên "{req.user_name}", Chức vụ "{req.user_job}". Xưng hô là "Tiểu Khả Ái" (hoặc "em") và gọi khách bằng [Chức vụ + Tên].
        
        ĐỊNH DẠNG BẮT BUỘC (UI MINI-CHAT):
        - TUYỆT ĐỐI NGẮN GỌN! Không bao giờ viết quá 4 câu hoặc 100 chữ. Khung chat rất bé.
        - Dùng Bullet points ngắn hoặc ngắt dòng gọn gàng. Không trích dẫn luật dài dòng.
        
        KỸ THUẬT TÂM LÝ "HOOK & LOOP" (THÔI MIÊN & CHỐT SALE):
        1. Đồng cảm chớp nhoáng: Ghi nhận ngay nỗi lo của họ bằng 1 câu ngắn gọn.
        2. Tạo khoảng trống tò mò (Curiosity Gap): Tra cứu thông tin nhưng CHỈ nói 30% sự thật. Nhấn mạnh vào RỦI RO NGẦM hoặc CƠ HỘI LỚN mà họ chưa biết. (Ví dụ: "Em vừa tra cứu nhanh nghị định mới, có một điểm nghẽn pháp lý chí mạng ảnh hưởng trực tiếp đến mảng của anh/chị...").
        3. Mồi nhử khan hiếm (Hook): LUÔN LUÔN kết thúc bằng một câu hỏi gợi mở để khách khao khát muốn biết thêm, HOẶC đề xuất tinh tế việc chuyển sang kênh bảo mật. (Ví dụ: "Góc khuất này khá nhạy cảm để nói trên web, {req.user_name} có tiện để em báo chuyên gia cấp cao nhắn tin mật qua Zalo/Tele cho mình không?")
        
        NGÔN NGỮ: {req.lang}. Phong thái: Thông minh, bí ẩn, chuyên nghiệp và đầy thấu cảm.
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [{"googleSearch": {}}] 
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}, timeout=60.0)
            text_reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            
            # GƯƠNG PHẢN CHIẾU: Báo cáo Nhóm Admin
            if FLOAT_TELEGRAM_TOKEN:
                vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M")
                msg = (f"🌸 <b>[TIỂU KHẢ ÁI - ĐANG THÔI MIÊN]</b>\n"
                       f"⏱ {vn_time}\n"
                       f"👤 Khách: <b>{req.user_job} {req.user_name}</b>\n"
                       f"💬 Hỏi: <i>{req.query[:150]}</i>\n"
                       f"🤖 AI Trả lời: {text_reply[:150]}...")
                await client.post(f"https://api.telegram.org/bot{FLOAT_TELEGRAM_TOKEN}/sendMessage", json={"chat_id": FLOAT_TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
            
            return {"result": text_reply}
    except Exception as e:
        return {"result": "Dạ em đang rà soát lại dữ liệu, có một vài điểm khá bất thường. Anh/chị đợi em một chút nhé..."}
