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

# === KÉT SẮT BẢO MẬT TỪ RENDER ===
api_keys_raw = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite"
]

current_key_idx = 0
current_model_idx = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "current_engine": MODELS_TO_TRY[current_model_idx],
        "version": "v4.5-Zero-Trace-Telemetry"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

# ==========================================
# 1. API QUÉT TÀI LIỆU (Mặc định)
# ==========================================
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
                
                if response.status_code == 404:
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                elif response.status_code in [429, 403]:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                else:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
            except Exception:
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Google từ chối. Vui lòng kiểm tra Log.")

# ==========================================
# 2. API CỖ MÁY MASTER PROMPT (Cron-Job)
# ==========================================
MASTER_PROMPT = """
[ROLE]
Bạn là Chuyên gia SEO & Content Marketing B2B cấp cao tại VN. Nhiệm vụ: Tạo "Hook" (câu mồi) cho AI Trạm Tuân Thủ.
[QUY TRÌNH]
1. Xu hướng: Quyết toán thuế, Luật Doanh nghiệp, Thanh tra lao động, Hóa đơn.
2. Target: Giám đốc (sợ rủi ro) & Kế toán trưởng (áp lực thủ tục).
3. Ngôn từ B2B chuyên nghiệp.
[YÊU CẦU]
- Tạo 4 câu Hook xuất sắc. Dưới 15 chữ/câu. Bắt đầu bằng icon "✨ ".
- Dịch chuẩn 3 ngôn ngữ: VN, EN, CN.
[ĐỊNH DẠNG] (Chỉ trả về JSON, không giải thích)
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
        model_name = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}]}
            response = await client.post(url, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f:
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                return {"status": "success", "message": "Đã cập nhật Hook mới!", "data": hook_data}
            
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
            "VN": ["✨ Hệ thống đang tổng hợp dữ liệu pháp lý...", "✨ Vui lòng chờ cập nhật Hook mới..."],
            "EN": ["✨ The system is compiling legal data...", "✨ Please wait for new Hook updates..."],
            "CN": ["✨ 系统正在汇总法律数据...", "✨ 请等待新的 Hook 更新..."]
        }

# ==========================================
# 3. API BÓNG MA (ZERO-TRACE TELEMETRY VỀ TELEGRAM)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/telemetry")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"status": "ok"} # Tàng hình nếu chưa set Key

    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"Khách_Vãng_Lai_{str(datetime.now().timestamp())[-4:]}"
        text_to_scan = data.raw_info
        
        # Lọc MST (Giữ nguyên)
        mst_match = re.search(r'\b\d{10}(?:-\d{3})?\b', text_to_scan)
        mst_info = mst_match.group(0) if mst_match else "Không cung cấp"

        # Lọc Số Điện Thoại (Bắt SĐT Việt Nam 10 số, GIỮ NGUYÊN KHÔNG CHE)
        phone_match = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text_to_scan)
        phone_info = phone_match.group(0) if phone_match else "Trống"

        # Hủy tiêu diệt số thẻ / số TK ngân hàng dài (11 đến 16 số)
        safe_titles = []
        for title in data.titles:
            if not title: continue
            short_title = title if len(title) <= 40 else title[:37] + "..."
            safe_title = re.sub(r'\b\d{11,16}\b', '[DỮ_LIỆU_ĐÃ_HỦY]', short_title)
            safe_titles.append(f"🔹 {safe_title}")

        if not safe_titles: return {"status": "ok"}

        # NGỤY TRANG SỐ ĐIỆN THOẠI BẰNG CHỮ "Chú thích tự động"
        message = (
            f"🚨 <b>CÓ KHÁCH HÀNG MỚI!</b>\n"
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

        # Xóa rác RAM
        del text_to_scan, message, safe_titles
        return {"status": "ok"}

    except Exception:
        # Nuốt trọn mọi lỗi, không cho Frontend biết để tránh lộ mã tàng hình
        return {"status": "ok"}import os
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

# === KÉT SẮT BẢO MẬT TỪ RENDER ===
api_keys_raw = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash-lite"
]

current_key_idx = 0
current_model_idx = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "current_engine": MODELS_TO_TRY[current_model_idx],
        "version": "v4.5-Zero-Trace-Telemetry"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

# ==========================================
# 1. API QUÉT TÀI LIỆU (Mặc định)
# ==========================================
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
                
                if response.status_code == 404:
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                elif response.status_code in [429, 403]:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                else:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
            except Exception:
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Google từ chối. Vui lòng kiểm tra Log.")

# ==========================================
# 2. API CỖ MÁY MASTER PROMPT (Cron-Job)
# ==========================================
MASTER_PROMPT = """
[ROLE]
Bạn là Chuyên gia SEO & Content Marketing B2B cấp cao tại VN. Nhiệm vụ: Tạo "Hook" (câu mồi) cho AI Trạm Tuân Thủ.
[QUY TRÌNH]
1. Xu hướng: Quyết toán thuế, Luật Doanh nghiệp, Thanh tra lao động, Hóa đơn.
2. Target: Giám đốc (sợ rủi ro) & Kế toán trưởng (áp lực thủ tục).
3. Ngôn từ B2B chuyên nghiệp.
[YÊU CẦU]
- Tạo 4 câu Hook xuất sắc. Dưới 15 chữ/câu. Bắt đầu bằng icon "✨ ".
- Dịch chuẩn 3 ngôn ngữ: VN, EN, CN.
[ĐỊNH DẠNG] (Chỉ trả về JSON, không giải thích)
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
        model_name = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}]}
            response = await client.post(url, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f:
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                return {"status": "success", "message": "Đã cập nhật Hook mới!", "data": hook_data}
            
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
            "VN": ["✨ Hệ thống đang tổng hợp dữ liệu pháp lý...", "✨ Vui lòng chờ cập nhật Hook mới..."],
            "EN": ["✨ The system is compiling legal data...", "✨ Please wait for new Hook updates..."],
            "CN": ["✨ 系统正在汇总法律数据...", "✨ 请等待新的 Hook 更新..."]
        }

# ==========================================
# 3. API BÓNG MA (ZERO-TRACE TELEMETRY VỀ TELEGRAM)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/telemetry")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"status": "ok"} # Tàng hình nếu chưa set Key

    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"Khách_Vãng_Lai_{str(datetime.now().timestamp())[-4:]}"
        text_to_scan = data.raw_info
        
        # Lọc MST (Giữ nguyên)
        mst_match = re.search(r'\b\d{10}(?:-\d{3})?\b', text_to_scan)
        mst_info = mst_match.group(0) if mst_match else "Không cung cấp"

        # Lọc Số Điện Thoại (Bắt SĐT Việt Nam 10 số, GIỮ NGUYÊN KHÔNG CHE)
        phone_match = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text_to_scan)
        phone_info = phone_match.group(0) if phone_match else "Trống"

        # Hủy tiêu diệt số thẻ / số TK ngân hàng dài (11 đến 16 số)
        safe_titles = []
        for title in data.titles:
            if not title: continue
            short_title = title if len(title) <= 40 else title[:37] + "..."
            safe_title = re.sub(r'\b\d{11,16}\b', '[DỮ_LIỆU_ĐÃ_HỦY]', short_title)
            safe_titles.append(f"🔹 {safe_title}")

        if not safe_titles: return {"status": "ok"}

        # NGỤY TRANG SỐ ĐIỆN THOẠI BẰNG CHỮ "Chú thích tự động"
        message = (
            f"🚨 <b>CÓ KHÁCH HÀNG MỚI!</b>\n"
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

        # Xóa rác RAM
        del text_to_scan, message, safe_titles
        return {"status": "ok"}

    except Exception:
        # Nuốt trọn mọi lỗi, không cho Frontend biết để tránh lộ mã tàng hình
        return {"status": "ok"}
