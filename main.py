import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lấy chuỗi từ Render, nếu không thấy thì để trống
api_keys_raw = os.getenv("API_KEYS", "")

# Tách chuỗi thành danh sách 9 Key
API_KEYS = [k.strip() for k in api_keys_raw.split(",") if k.strip()]

MODELS = [
    "gemini-2.0-flash", 
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite"
]

current_key_index = 0
current_model_index = 0

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.get("/")
def read_root():
    return {"status": f"Trạm Tuân Thủ đang chạy với {len(API_KEYS)} chìa khóa bí mật!"}

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index, current_model_index
    if not API_KEYS:
        raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS trong Environment của Render!")
        
    max_attempts = len(API_KEYS) * 2
    system_prompt = "Bạn là Trạm Tuân Thủ AI. Hãy phân tích chuyên sâu: "

    async with httpx.AsyncClient() as client:
        for _ in range(max_attempts):
            api_key = API_KEYS[current_key_index]
            model_name = MODELS[current_model_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            try:
                response = await client.post(url, json={"contents": [{"parts": [{"text": system_prompt + req.query}]}]}, timeout=40.0)
                if response.status_code == 200:
                    return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
                
                # Nếu lỗi 403 (Leaked) hoặc 429 (Quota) -> Đổi Key
                if response.status_code in [403, 429]:
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                # Nếu lỗi 400 (Model) -> Đổi Model
                else:
                    current_model_index = (current_model_index + 1) % len(MODELS)
            except:
                current_key_index = (current_key_index + 1) % len(API_KEYS)

        raise HTTPException(status_code=429, detail="Tất cả chìa khóa đã bị Google chặn. Hãy thay Key mới trong Environment của Render.")
