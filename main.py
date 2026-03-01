from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging

app = FastAPI()

# Mở cửa cho Figma kết nối vào máy chủ này
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# KHO CHỨA API KEYS (Mèo Già dán đè Key thật vào đây)
# =================================================================
API_KEYS = [
    "AIzaSyDOOiKriEsblDufKeZ7VdhCrazDPlNn4jI",
    "AIzaSyBBym7nCqUTMUl3vuzspoNFqC-3Tr2quxg",
    "AIzaSyD66QktNtrc1ZZXsbXIkDx3Uzi_GnNXm3s"
]
current_key_index = 0

# Đổi về 2.0-flash để đảm bảo tương thích 100% với Free Tier
MODEL_NAME = "gemini-2.0-flash"

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.get("/")
def read_root():
    return {"status": "Trạm Tuân Thủ API đang chạy 24/7!"}

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index
    attempts = 0
    max_attempts = len(API_KEYS)

    system_prompt = f"""Bạn là "Trạm Tuân Thủ AI", một chuyên gia pháp lý, kế toán trưởng cấp cao tại Việt Nam. 
    Hãy trả lời thẳng vào vấn đề, phân tích rủi ro theo luật hiện hành. 
    Format bằng Markdown, dùng danh sách, in đậm ý chính. Không cần mở bài dài dòng.
    \nCông cụ đang dùng: [{req.tool}]. Hãy tập trung phân tích theo công cụ này.
    \nCâu hỏi: """

    payload = {
        "contents": [{"parts": [{"text": system_prompt + req.query}]}]
    }

    async with httpx.AsyncClient() as client:
        while attempts < max_attempts:
            api_key = API_KEYS[current_key_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"
            
            try:
                response = await client.post(url, json=payload, timeout=40.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"result": data["candidates"][0]["content"]["parts"][0]["text"]}
                
                else: # Đã gộp mọi lỗi (400, 403, 404, 429) vào đây để phân tích
                    print("="*40)
                    print(f"LỖI TẠI KEY SỐ: {current_key_index + 1}")
                    print(f"Mã lỗi HTTP: {response.status_code}")
                    print(f"Lý do Google từ chối: {response.text}") # <--- DÒNG NỘI SOI NÀY RẤT QUAN TRỌNG
                    print("="*40)
                    
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                    attempts += 1
                    
            except Exception as e:
                print(f"Lỗi mạng: {str(e)}. Thử Key tiếp theo...")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                attempts += 1

        raise HTTPException(status_code=429, detail="Tất cả API Keys đều thất bại. Vui lòng kiểm tra Log trên Render để xem lý do Google từ chối.")
