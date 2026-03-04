import os
import json
import httpx
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

# LẤY 9 API KEYS TỪ KÉT SẮT RENDER
api_keys_raw = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]

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
        "version": "v4.1-Smart-Fallback-Hooks"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

# ==========================================
# 1. API QUÉT TÀI LIỆU (Giữ nguyên logic cũ của Giám đốc)
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
                
                print(f"--- THỬ: Key {current_key_idx+1} | Model {model_name} | Lỗi {response.status_code} ---")
                if response.status_code == 404:
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                elif response.status_code in [429, 403]:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                else:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
            except Exception as e:
                print(f"Lỗi mạng: {str(e)}")
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Google từ chối. Vui lòng kiểm tra Log.")

# ==========================================
# 2. CỖ MÁY MASTER PROMPT (Dành cho Cron-Job)
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
    global current_key_idx, current_model_idx
    if not API_KEYS: return {"status": "error", "message": "No API Keys"}

    async with httpx.AsyncClient() as client:
        # Lấy Key hiện tại (Hưởng lợi từ vòng xoay của hệ thống chính)
        api_key = API_KEYS[current_key_idx]
        model_name = "gemini-1.5-flash" # Dùng bản Flash cho nhanh và rẻ
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}]}
            response = await client.post(url, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                # Cắt bỏ các ký tự Markdown thừa để lấy chuẩn JSON
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                
                # Lưu vào file nội bộ trên máy chủ Render
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f:
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
                    
                # Tịnh tiến Key cho lần gọi sau
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                return {"status": "success", "message": "Đã cập nhật Hook mới!", "data": hook_data}
            
            # Nếu Key lỗi, tự động tịnh tiến sang Key khác
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error", "code": response.status_code}
            
        except Exception as e:
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error", "message": str(e)}

# ==========================================
# 3. API ĐỂ TRẢ DỮ LIỆU CHO HERO CHAT
# ==========================================
@app.get("/api/hooks")
def get_hooks():
    try:
        # Đọc file đã được cron-job tạo ra
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        # Dự phòng nếu chưa tới giờ cron-job chạy lần nào
        return {
            "VN": ["✨ Hệ thống đang tổng hợp dữ liệu pháp lý...", "✨ Vui lòng chờ cập nhật Hook mới..."],
            "EN": ["✨ The system is compiling legal data...", "✨ Please wait for new Hook updates..."],
            "CN": ["✨ 系统正在汇总法律数据...", "✨ 请等待新的 Hook 更新..."]
        }
