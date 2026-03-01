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

# LẤY 9 API KEYS TỪ KÉT SẮT RENDER (Khu vực Environment Variables)
api_keys_raw = os.getenv("API_KEYS", "")
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]

# Danh sách model ổn định nhất theo tài liệu Mèo Già cung cấp
MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

current_key_index = 0
current_model_index = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "engine": "Trạm Tuân Thủ v2.0"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index, current_model_index
    
    if not API_KEYS:
        print("!!! CẢNH BÁO: Không tìm thấy API_KEYS trong cấu hình Render !!!")
        raise HTTPException(status_code=500, detail="Máy chủ chưa được cấu hình API Keys.")

    # Thử tối đa qua nhiều Key và Model
    max_attempts = len(API_KEYS) * 2
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            api_key = API_KEYS[current_key_index]
            model_name = MODELS[current_model_index]
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            try:
                # Prompt chuyên gia cho Mèo Già
                system_prompt = f"Bạn là Trạm Tuân Thủ AI. Công cụ: {req.tool}. Hãy phân tích: "
                payload = {"contents": [{"parts": [{"text": system_prompt + req.query}]}]}
                
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"result": data["candidates"][0]["content"]["parts"][0]["text"]}
                
                # In lỗi để theo dõi
                print(f"Lần thử {attempt+1}: Key {current_key_index}, Model {model_name}, Status {response.status_code}")
                
                # Logic xoay vòng: Nếu 429/403 (Lỗi Key) -> Đổi Key. Nếu lỗi khác -> Đổi Model.
                if response.status_code in [429, 403]:
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                else:
                    current_model_index = (current_model_index + 1) % len(MODELS)
                    
            except Exception as e:
                print(f"Lỗi kết nối: {str(e)}")
                current_key_index = (current_key_index + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Tất cả tài nguyên AI tạm thời không phản hồi.")
