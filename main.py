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

# THAY ĐỔI CHIẾN THUẬT: Dùng 1.5-flash làm chủ đạo vì 2.0 đang bị khóa hạn mức
MODELS = ["gemini-1.5-flash", "gemini-1.5-pro"]

current_key_index = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "engine": "Trạm Tuân Thủ v3.0 - 1.5 Flash Engine"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index
    
    if not API_KEYS:
        raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS!")

    # Thử quét qua tất cả 9 Keys nếu cần
    max_attempts = len(API_KEYS)
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            api_key = API_KEYS[current_key_index]
            # ÉP DÙNG 1.5 FLASH ĐỂ VƯỢT LỖI LIMIT 0 CỦA BẢN 2.0
            model_name = "gemini-1.5-flash" 
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            try:
                system_prompt = f"Bạn là Trạm Tuân Thủ AI chuyên gia pháp lý. Hãy phân tích chuyên sâu: "
                payload = {"contents": [{"parts": [{"text": system_prompt + req.query}]}]}
                
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"result": data["candidates"][0]["content"]["parts"][0]["text"]}
                
                # In lỗi chi tiết để Giám đốc theo dõi trên Render
                print(f"Key {current_key_index + 1} thất bại. Mã lỗi: {response.status_code}")
                
                # Xoay vòng Key
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                
            except Exception as e:
                print(f"Lỗi kết nối: {str(e)}")
                current_key_index = (current_key_index + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Google đang giới hạn gắt gao Project này. Giám đốc hãy thử lại sau 1 phút hoặc tạo Key từ Gmail khác.")
