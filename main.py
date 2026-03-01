from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import logging

app = FastAPI()

# Mở cửa cho Figma kết nối vào máy chủ này
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hỗ trợ mọi tên miền
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# KHO CHỨA API KEYS (MÈO GIÀ DÁN KEY THẬT VÀO ĐÂY)
# =================================================================
API_KEYS = [
    "AIzaSyAWtQMxNcXbTu0KEuhHKBlPmpLlvD1A9ok", 
    "AIzaSyBziWuaPjqp-o7rvJzcurVuwchKrXUMdSM", 
    "AIzaSyBkHtDHgm81ofcf1FwLcuhhoVui8aiKJww",
    "AIzaSyAZTJzPY-TuVvbYn5FjVk9gYmenX1Bp7Do",
    "AIzaSyC7Ar7Tvx1kv3Q17X8KuSewW2uuUbLjT9k",
    "AIzaSyC3HXeDNeu8DJvJQ417k43booxRGQZhoPw",
    "AIzaSyBKBNaNFZLyFFKSarnYff7Mkwclly_9faw",
    "AIzaSyCDGcg5JNjCvz8IDtsvsWcRZXzrhuW25VA",
    "AIzaSyBmHm0PZfLo5DCWL76NlXVYPUxEsmiCxhg"
    
]

# =================================================================
# DANH SÁCH ĐỘNG CƠ DỰ PHÒNG (Dựa theo file model_gemini_free.txt)
# =================================================================
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite"
]

current_key_index = 0
current_model_index = 0

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.get("/")
def read_root():
    return {"status": "Trạm Tuân Thủ API đang chạy 24/7 với Xoay vòng Kép!"}

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_index, current_model_index
    max_attempts = 5 # Thử tối đa 5 lần lách lỗi

    system_prompt = f"""Bạn là "Trạm Tuân Thủ AI", một chuyên gia pháp lý, kế toán trưởng cấp cao tại Việt Nam. 
    Hãy trả lời thẳng vào vấn đề, phân tích rủi ro theo luật hiện hành. 
    Format bằng Markdown, dùng danh sách, in đậm ý chính. Không cần mở bài dài dòng.
    \nCông cụ đang dùng: [{req.tool}]. Hãy tập trung phân tích theo công cụ này.
    \nCâu hỏi: """

    payload = {
        "contents": [{"parts": [{"text": system_prompt + req.query}]}]
    }

    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            api_key = API_KEYS[current_key_index]
            model_name = MODELS[current_model_index]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            try:
                response = await client.post(url, json=payload, timeout=40.0)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"result": data["candidates"][0]["content"]["parts"][0]["text"]}
                
                else:
                    # In lỗi ra màn hình Render để gỡ rối
                    print(f"--- LẦN THỬ {attempt + 1} THẤT BẠI ---")
                    print(f"Key: {api_key[:10]}... | Model: {model_name} | Mã lỗi: {response.status_code}")
                    print(f"Lý do Google từ chối: {response.text}")
                    
                    # Nếu lỗi do Hết Quota (429) hoặc Cấm (403) -> Đổi Key
                    if response.status_code in [429, 403]:
                        current_key_index = (current_key_index + 1) % len(API_KEYS)
                    # Nếu lỗi do Động cơ không tồn tại (404, 400) -> Đổi Động cơ
                    elif response.status_code in [404, 400]:
                        current_model_index = (current_model_index + 1) % len(MODELS)
                    else:
                        current_key_index = (current_key_index + 1) % len(API_KEYS)
                        current_model_index = (current_model_index + 1) % len(MODELS)
                        
            except Exception as e:
                print(f"Lỗi mạng/Timeout: {str(e)}")
                current_key_index = (current_key_index + 1) % len(API_KEYS)

        raise HTTPException(status_code=429, detail="Hệ thống đã thử xoay vòng cả API Key và Model nhưng đều bị Google từ chối. Vui lòng kiểm tra màn hình Log trên Render để xem lý do chi tiết.")
