import os
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

# DANH SÁCH ĐỘNG CƠ DỰ PHÒNG (Lấy chính xác từ danh sách của Mèo Già)
# Chúng ta sẽ thử bản 2.0 trước, nếu 404 sẽ thử bản Flash-latest
MODELS_TO_TRY = [
    "gemini-2.0-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-pro-latest"
]

current_key_idx = 0
current_model_idx = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "current_engine": MODELS_TO_TRY[current_model_idx],
        "version": "v4.0-Smart-Fallback"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_idx, current_model_idx
    
    if not API_KEYS:
        raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS!")

    # Tổng số lần thử tối đa = Số Key x Số Model
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
                
                # IN LOG CHI TIẾT ĐỂ GIÁM ĐỐC THEO DÕI
                print(f"--- THỬ: Key {current_key_idx+1} | Model {model_name} | Lỗi {response.status_code} ---")

                # CHIẾN THUẬT XOAY VÒNG THÔNG MINH:
                if response.status_code == 404:
                    # Nếu sai tên model -> Đổi sang model tiếp theo trong danh sách
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                elif response.status_code in [429, 403]:
                    # Nếu hết lượt hoặc bị chặn -> Đổi sang chìa khóa tiếp theo
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                else:
                    # Các lỗi khác -> Đổi cả hai cho chắc
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    current_model_idx = (current_model_idx + 1) % len(MODELS_TO_TRY)
                    
            except Exception as e:
                print(f"Lỗi mạng: {str(e)}")
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Đã thử mọi tổ hợp Key và Model nhưng Google vẫn từ chối. Giám đốc hãy kiểm tra lại Log.")
