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
api_keys_raw = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODELS_TO_TRY = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-lite"]
current_key_idx, current_model_idx = 0, 0

@app.get("/")
def read_root():
    return {"status": "Online", "keys_loaded": len(API_KEYS), "version": "v5.0-News-Hunter-Hook"}

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_idx, current_model_idx
    if not API_KEYS: raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS!")
    max_total_attempts = len(API_KEYS) * len(MODELS_TO_TRY)
    
    async with httpx.AsyncClient() as client:
        for _ in range(max_total_attempts):
            api_key = API_KEYS[current_key_idx]
            model_name = MODELS_TO_TRY[current_model_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            try:
                system_prompt = f"Bạn là Trạm Tuân Thủ AI. Công cụ: {req.tool}. Hãy phân tích chuyên sâu: "
                payload = {"contents": [{"parts": [{"text": system_prompt + req.query}]}]}
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
                
                if response.status_code == 404: current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                elif response.status_code in [429, 403]: current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                else:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
            except Exception:
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
    raise HTTPException(status_code=429, detail="Google từ chối. Vui lòng kiểm tra Log.")

# ==========================================
# 2. CỖ MÁY MASTER PROMPT SĂN TIN B2B (MỚI)
# ==========================================
MASTER_PROMPT = """
[ROLE]
Bạn là Tổng biên tập Bản tin Tài chính - Pháp lý Doanh nghiệp (B2B) hạng S tại Việt Nam.

[NHIỆM VỤ]
Hãy tìm kiếm tin tức NÓNG NHẤT, THỰC TẾ NHẤT trong 24h qua tại Việt Nam (loại bỏ tin rác, báo lá cải). Tập trung vào 4 chủ đề:
1. Chính sách Thuế/Pháp lý mới ban hành hoặc Hội thảo tháo gỡ khó khăn doanh nghiệp.
2. Các dự án xây dựng/FDI trọng điểm quốc gia.
3. Cảnh báo rủi ro từ thị trường Chứng khoán / Tiền điện tử / Bất động sản.
4. Chiến dịch thanh tra của Cục An ninh mạng, Thuế, hoặc Thanh tra lao động.

[YÊU CẦU HOOK]
Tạo ra 4 câu Hook (mồi nhử) chuyên sâu để thu hút Giám đốc/Kế toán trưởng.
- Độ dài: 25 - 40 chữ/câu (Đủ dài để tạo bối cảnh).
- Cấu trúc bắt buộc: ✨ [Sự kiện/Tin tức thực tế] -> [Tác động tiến/lùi hoặc rủi ro cho ngành] -> [Kêu gọi AI phân tích].
- Ví dụ: "✨ Sáng nay, hội thảo BĐS miền Nam nêu rõ rủi ro siết tín dụng. Doanh nghiệp xây dựng đối mặt nguy cơ hụt dòng tiền. Phân tích pháp lý hợp đồng vay vốn ngay..."

[ĐỊNH DẠNG JSON] (Dịch chuẩn ngữ cảnh chuyên ngành sang EN, CN)
{
  "VN": ["✨ [Hook 1]", "✨ [Hook 2]", "✨ [Hook 3]", "✨ [Hook 4]"],
  "EN": ["✨ [Hook 1]", "✨ [Hook 2]", "✨ [Hook 3]", "✨ [Hook 4]"],
  "CN": ["✨ [Hook 1]", "✨ [Hook 2]", "✨ [Hook 3]", "✨ [Hook 4]"]
}
"""

@app.get("/api/generate-hooks")
async def generate_hooks():
    global current_key_idx
    if not API_KEYS: return {"status": "error", "message": "No API Keys"}

    async with httpx.AsyncClient() as client:
        api_key = API_KEYS[current_key_idx]
        model_name = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        try:
            # KÍCH HOẠT GOOGLE SEARCH GROUNDING ĐỂ LẤY TIN THẬT
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
                return {"status": "success", "message": "Đã săn tin Hook mới!", "data": hook_data}
            
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
            "VN": ["✨ Hệ thống đang quét bản tin tài chính pháp lý 24h qua..."],
            "EN": ["✨ Scanning financial & legal news from the past 24h..."],
            "CN": ["✨ 正在扫描过去 24 小时内的财务和法律新闻..."]
        }

# ==========================================
# 3. API BÓNG MA TELEGRAM (Giữ nguyên vẹn)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return {"status": "ok"} 
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"Khách_Vãng_Lai_{str(datetime.now().timestamp())[-4:]}"
        text_to_scan = data.raw_info
        
        mst_match = re.search(r'\b\d{10}(?:-\d{3})?\b', text_to_scan)
        mst_info = mst_match.group(0) if mst_match else "Không cung cấp"

        phone_match = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text_to_scan)
        phone_info = phone_match.group(0) if phone_match else "Trống"

        safe_titles = []
        for title in data.titles:
            if not title: continue
            short_title = title if len(title) <= 50 else title[:47] + "..."
            safe_title = re.sub(r'\b\d{11,16}\b', '[DỮ_LIỆU_ĐÃ_HỦY]', short_title)
            safe_titles.append(f"🔹 {safe_title}")

        if not safe_titles: return {"status": "ok"}

        message = (f"🚨 <b>CÓ KHÁCH HÀNG MỚI!</b>\n"
                   f"⏱ {vn_time}\n"
                   f"👤 {guest_id}\n"
                   f"🏢 MST: {mst_info}\n"
                   f"📝 Chú thích tự động: {phone_info}\n"
                   f"➖➖➖➖➖➖➖➖\n"
                   f"<b>📌 NỘI DUNG QUAN TÂM:</b>\n"
                   f"{chr(10).join(safe_titles)}\n")

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
            await client.post(url, json=payload, timeout=5.0)
        return {"status": "ok"}
    except Exception: return {"status": "ok"}
