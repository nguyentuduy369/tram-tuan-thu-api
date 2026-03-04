import os
import json
import httpx
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === KÉT SẮT BẢO MẬT ===
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# THÔNG TIN VERTEX AI AGENT (LỄ TÂN)
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "679561966812")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")
GCP_AGENT_ID = os.getenv("GCP_AGENT_ID", "") # Dán Agent ID của Lễ Tân vào Render

@app.get("/")
def read_root():
    return {"status": "Online", "version": "v7.0-Divine-Receptionist-Integrated"}

# ==========================================
# 1. CỖ MÁY MASTER PROMPT SĂN TIN B2B CẤP CAO
# ==========================================
MASTER_PROMPT = """
[ROLE]
Bạn là Tổng biên tập Bản tin Chiến lược Doanh nghiệp B2B hạng S.

[MISSION]
Tìm kiếm và tổng hợp tin tức nóng nhất trong 24h qua tại VN về:
- Dự án trọng điểm quốc gia, công trình lớn đang triển khai.
- Hội thảo tháo gỡ khó khăn doanh nghiệp, dự thảo luật 2025-2026.
- Biến động chứng khoán rủi ro, kế hoạch của Cục An ninh mạng/Thuế.

[HOOK REQUIREMENTS]
Tạo 4 câu Hook chuyên sâu, dài 25-40 chữ.
Cấu trúc: ✨ [Bối cảnh thời sự thật] -> [Phân tích rủi ro/tiến lùi của ngành] -> [Lời mời gọi AI phân tích].
Ví dụ: "✨ Sáng nay, hội thảo doanh nghiệp miền Nam thảo luận về dự án cao tốc mới. Ngành xây dựng đối mặt thách thức chi phí vật liệu tăng cao. Hãy đặt câu hỏi để AI tầm soát rủi ro hợp đồng thầu..."

[OUTPUT JSON]
{
  "VN": ["✨ Hook 1", "✨ Hook 2", "✨ Hook 3", "✨ Hook 4"],
  "EN": ["✨ [Dịch chuyên ngành]", "✨ ..."],
  "CN": ["✨ [Dịch chuyên ngành]", "✨ ..."]
}
"""

@app.get("/api/generate-hooks")
async def generate_hooks():
    if not API_KEYS: return {"status": "error"}
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[0]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}], "tools": [{"googleSearch": {}}]}
            response = await client.post(url, json=payload, timeout=45.0)
            if response.status_code == 200:
                hook_data = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"].replace("```json", "").replace("```", "").strip())
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f:
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
                return {"status": "success", "data": hook_data}
        except: pass
    return {"status": "error"}

@app.get("/api/hooks")
def get_hooks():
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f: return json.load(f)
    except: return {"VN": ["✨ Đang săn tin tức pháp lý thời thực cho doanh nghiệp..."]}

# ==========================================
# 2. KẾT NỐI LÕI LỄ TÂN (VERTEX AI AGENT)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY or not GCP_AGENT_ID:
        return {"result": "Hệ thống Lễ Tân đang bảo trì ID. Vui lòng quay lại sau!"}
    
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as AuthRequest
        
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        url = f"https://{GCP_LOCATION}-dialogflow.googleapis.com/v3/projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/agents/{GCP_AGENT_ID}/sessions/{req.session_id}:detectIntent"
        headers = {"Authorization": f"Bearer {scoped_creds.token}", "Content-Type": "application/json"}
        payload = {"queryInput": {"text": {"text": req.query}, "languageCode": "vi"}}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            if response.status_code == 200:
                messages = response.json().get("queryResult", {}).get("responseMessages", [])
                full_reply = "".join(["\n".join(m["text"]["text"]) for m in messages if "text" in m])
                return {"result": full_reply or "Lễ Tân đang suy nghĩ, vui lòng nhắc lại."}
            return {"result": f"Lễ Tân gặp sự cố kết nối: {response.status_code}"}
    except Exception as e:
        return {"result": f"Lỗi hệ thống: {str(e)}"}

# ==========================================
# 3. BÁO CÁO TELEGRAM (BÓNG MA)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def sync_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        text = data.raw_info
        mst = re.search(r'\b\d{10}(?:-\d{3})?\b', text)
        phone = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text)
        
        message = (
            f"🚨 <b>BÁO CÁO TRẢI NGHIỆM MỚI</b>\n"
            f"⏱ {vn_time}\n"
            f"🏢 MST: {mst.group(0) if mst else 'Trống'}\n"
            f"📝 Chú thích tự động: {phone.group(0) if phone else 'Trống'}\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"<b>📌 QUAN TÂM:</b>\n"
            f"{chr(10).join([f'🔹 {t}' for t in data.titles])}"
        )
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                              json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except: pass
    return {"status": "ok"}
