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

# Danh sách Model an toàn nhất (Dựa trên PDF Giám đốc cung cấp)
MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

current_key_index = 0

@app.get("/")
def read_root():
    return {
        "status": "Online",
        "keys_loaded": len(API_KEYS),
        "engine": "Trạm Tuân Thủ v2.5 Debug Mode"
    }

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index
    
    if not API_KEYS:
        raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS trong Environment của Render!")

    # Thử quét qua tất cả 9 Keys
    max_attempts = len(API_KEYS)
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            api_key = API_KEYS[current_key_index]
            # Thử model 2.0-flash trước vì nó mạnh nhất trong danh sách của Giám đốc
            model_name = "gemini-2.0-flash" 
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            try:
                system_prompt = f"Bạn là Trạm Tuân Thủ AI. Hãy phân tích: "
                payload = {"contents": [{"parts": [{"text": system_prompt + req.query}]}]}
                
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"result": data["candidates"][0]["content"]["parts"][0]["text"]}
                
                # NẾU THẤT BẠI: In lỗi cực chi tiết ra Log Render
                print(f"--- THỬ KEY SỐ {current_key_index + 1} THẤT BẠI ---")
                print(f"Mã lỗi HTTP: {response.status_code}")
                print(f"Lý do Google từ chối: {response.text}") # <--- ĐÂY LÀ DÒNG CHÚNG TA CẦN ĐỌC
                
                # Xoay vòng sang Key tiếp theo
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                
            except Exception as e:
                print(f"Lỗi kết nối mạng: {str(e)}")
                current_key_index = (current_key_index + 1) % len(API_KEYS)

    raise HTTPException(status_code=429, detail="Cả 9 Key đều bị Google từ chối. Giám đốc hãy xem Log trên Render để biết lý do tiếng Anh là gì!")
