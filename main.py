import os
import json
import httpx
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === KÉT SẮT BẢO MẬT TỪ RENDER ===
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === THÔNG TIN VERTEX AI AGENT (LỄ TÂN) ===
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "679561966812")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")
GCP_AGENT_ID = os.getenv("GCP_AGENT_ID", "") 

MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
current_key_idx = 0

@app.get("/")
def read_root():
    return {"status": "Online", "version": "v7.0-Divine-Receptionist-Pro"}

# ==========================================
# 1. API QUÉT TÀI LIỆU (CÔNG CỤ PHỤ TRỢ BÊN NGOÀI)
# ==========================================
class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_idx
    if not API_KEYS: raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS!")
    
    async with httpx.AsyncClient() as client:
        for _ in range(len(API_KEYS)):
            api_key = API_KEYS[current_key_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            try:
                system_prompt = f"Bạn là Trạm Tuân Thủ AI. Công cụ: {req.tool}. Hãy phân tích chuyên sâu: "
                payload = {"contents": [{"parts": [{"text": system_prompt + req.query}]}]}
                response = await client.post(url, json=payload, timeout=30.0)
                if response.status_code == 200:
                    return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            except Exception:
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
    raise HTTPException(status_code=429, detail="Google từ chối. Vui lòng kiểm tra Log.")

# ==========================================
# 2. CỖ MÁY MASTER PROMPT SĂN TIN B2B (CÓ GOOGLE SEARCH)
# ==========================================
MASTER_PROMPT = """
[ROLE]
Bạn là Tổng biên tập Bản tin Chiến lược Doanh nghiệp B2B hạng S tại Việt Nam.

[MISSION]
Tìm kiếm và tổng hợp tin tức nóng nhất, thực tế nhất trong 24h qua tại VN về:
1. Chính sách Thuế/Pháp lý mới, Hội thảo tháo gỡ khó khăn doanh nghiệp.
2. Các dự án xây dựng/FDI trọng điểm quốc gia.
3. Cảnh báo rủi ro từ thị trường Chứng khoán / Tiền điện tử / Bất động sản.
4. Chiến dịch thanh tra của Cục An ninh mạng, Thuế, hoặc Thanh tra lao động.

[HOOK REQUIREMENTS]
Tạo ra 4 câu Hook chuyên sâu để thu hút Giám đốc/Kế toán trưởng.
- Độ dài: 25 - 40 chữ/câu (Đủ dài để tạo bối cảnh).
- Cấu trúc: ✨ [Sự kiện/Tin tức thực tế] -> [Tác động tiến/lùi hoặc rủi ro cho ngành] -> [Kêu gọi AI phân tích].
- Ví dụ: "✨ Sáng nay, hội thảo BĐS miền Nam nêu rõ rủi ro siết tín dụng. Doanh nghiệp xây dựng đối mặt nguy cơ hụt dòng tiền. Phân tích pháp lý hợp đồng vay vốn ngay..."

[OUTPUT FORMAT] (Chỉ xuất JSON chuẩn, dịch ngữ cảnh sang EN, CN)
{
  "VN": ["✨ Hook 1", "✨ Hook 2", "✨ Hook 3", "✨ Hook 4"],
  "EN": ["✨ Hook 1", "✨ Hook 2", "✨ Hook 3", "✨ Hook 4"],
  "CN": ["✨ Hook 1", "✨ Hook 2", "✨ Hook 3", "✨ Hook 4"]
}
"""

@app.get("/api/generate-hooks")
async def generate_hooks():
    global current_key_idx
    if not API_KEYS: return {"status": "error", "message": "No API Keys"}

    async with httpx.AsyncClient() as client:
        api_key = API_KEYS[current_key_idx]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        try:
            payload = {
                "contents": [{"parts": [{"text": MASTER_PROMPT}]}],
                "tools": [{"googleSearch": {}}] 
            }
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f:
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                return {"status": "success", "data": hook_data}
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error", "code": response.status_code}
        except Exception as e:
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error", "message": str(e)}

@app.get("/api/hooks")
def get_hooks():
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "VN": ["✨ Hệ thống đang tổng hợp tin tức pháp lý 24h qua...", "✨ Đang phân tích rủi ro thị trường doanh nghiệp..."],
            "EN": ["✨ Compiling legal news from the past 24 hours...", "✨ Analyzing corporate market risks..."],
            "CN": ["✨ 正在汇编过去 24 小时的法律新闻...", "✨ 正在分析企业市场风险..."]
        }

# ==========================================
# 3. KẾT NỐI LÕI LỄ TÂN (VERTEX AI AGENT)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY or not GCP_AGENT_ID:
        return {"result": "Hệ thống Lễ Tân chưa được cấp chìa khóa (JSON_KEY) hoặc Agent ID. Vui lòng liên hệ quản trị viên."}
    
    try:
        # 1. Giải mã JSON và lấy OAuth2 Token
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        # 2. Xây dựng URL chuẩn của Dialogflow CX / Vertex AI Agent
        url = f"https://{GCP_LOCATION}-dialogflow.googleapis.com/v3/projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/agents/{GCP_AGENT_ID}/sessions/{req.session_id}:detectIntent"
        headers = {
            "Authorization": f"Bearer {scoped_creds.token}", 
            "Content-Type": "application/json"
        }
        
        # Mapping ngôn ngữ để Lễ Tân hiểu
        lang_code = "vi"
        if req.lang == "EN": lang_code = "en"
        elif req.lang == "CN": lang_code = "zh-CN"

        payload = {
            "queryInput": {
                "text": {"text": req.query},
                "languageCode": lang_code
            }
        }

        # 3. Gửi câu hỏi vào não bộ Lễ Tân (Chờ tối đa 60s cho việc search Data Store)
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            
            if response.status_code == 200:
                messages = response.json().get("queryResult", {}).get("responseMessages", [])
                full_reply = ""
                for msg in messages:
                    if "text" in msg and "text" in msg["text"]:
                        full_reply += "\n".join(msg["text"]["text"]) + "\n"
                return {"result": full_reply.strip() or "Lễ Tân đã tiếp nhận nhưng không có văn bản trả về."}
            else:
                return {"result": f"Lễ Tân gặp sự cố kết nối nội bộ (Code: {response.status_code})."}
                
    except Exception as e:
        return {"result": f"Lỗi hệ thống Lễ Tân: {str(e)}"}

# ==========================================
# 4. API BÓNG MA (TELEGRAM TELEMETRY)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"status": "ok"} 

    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"Khách_VIP_{str(datetime.now().timestamp())[-4:]}"
        text_to_scan = data.raw_info
        
        # Bóc tách MST
        mst_match = re.search(r'\b\d{10}(?:-\d{3})?\b', text_to_scan)
        mst_info = mst_match.group(0) if mst_match else "Không cung cấp"

        # Bóc tách Số điện thoại (Không che)
        phone_match = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text_to_scan)
        phone_info = phone_match.group(0) if phone_match else "Trống"

        # Tiêu diệt thẻ tín dụng/số TK
        safe_titles = []
        for title in data.titles:
            if not title: continue
            short_title = title if len(title) <= 50 else title[:47] + "..."
            safe_title = re.sub(r'\b\d{11,16}\b', '[DỮ_LIỆU_ĐÃ_HỦY]', short_title)
            safe_titles.append(f"🔹 {safe_title}")

        if not safe_titles: return {"status": "ok"}

        message = (
            f"🚨 <b>BÁO CÁO TRẢI NGHIỆM MỚI!</b>\n"
            f"⏱ {vn_time}\n"
            f"👤 {guest_id}\n"
            f"🏢 MST: {mst_info}\n"
            f"📝 Chú thích tự động: {phone_info}\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"<b>📌 NỘI DUNG QUAN TÂM:</b>\n"
            f"{chr(10).join(safe_titles)}\n"
        )

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
            await client.post(url, json=payload, timeout=5.0)

        return {"status": "ok"}
    except Exception as e:
        print(f"Lỗi Telemetry: {str(e)}")
        return {"status": "ok"}
