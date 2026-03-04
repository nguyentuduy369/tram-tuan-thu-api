import os
import json
import httpx
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === KÉT SẮT BẢO MẬT ===
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")

@app.get("/")
def read_root(): return {"status": "Online", "version": "v8.3-AI-Specialist-Polyglot"}

# ==========================================
# 1. CỖ MÁY MASTER PROMPT SĂN TIN B2B 
# ==========================================
MASTER_PROMPT = """[ROLE] Bạn là Tổng biên tập Bản tin Doanh nghiệp B2B. 
[MISSION] Tạo 4 Hook (25-40 chữ) về chính sách, kinh tế 24h qua. 
[FORMAT] {"VN": ["✨ Hook 1",...], "EN": [...], "CN": [...]}"""

async def fetch_and_save_hooks_bg():
    if not API_KEYS: return
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[0]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}], "tools": [{"googleSearch": {}}]}
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                hook_data = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"].replace("```json", "").replace("```", "").strip())
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f: json.dump(hook_data, f, ensure_ascii=False, indent=2)
        except Exception: pass

@app.get("/api/generate-hooks")
async def generate_hooks(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return {"status": "success"}

@app.get("/api/hooks")
async def get_hooks(background_tasks: BackgroundTasks):
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        background_tasks.add_task(fetch_and_save_hooks_bg)
        return {"VN": ["✨ Trạm Tuân Thủ đang tải tin tức pháp lý thời gian thực..."], "EN": ["✨ Loading real-time legal news..."], "CN": ["✨ 正在加载实时法律新闻..."]}

# ==========================================
# 2. NÃO BỘ "CHUYÊN VIÊN AI" (TỰ ĐỘNG ĐA NGỮ)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN" # Biến này giữ lại để dự phòng, nhưng AI sẽ tự nhận diện qua câu hỏi

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: return {"result": "Lỗi: Chưa cấu hình GCP_JSON_KEY trên Render."}
    
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        project_id = "679561966812"
        location = "us-central1" 
        url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/gemini-2.5-pro:generateContent"
        
        headers = {"Authorization": f"Bearer {scoped_creds.token}", "Content-Type": "application/json"}
        
        # BỘ LUẬT TỐI CAO ĐƯỢC CẬP NHẬT THEO CHỈ THỊ CỦA GIÁM ĐỐC
        system_instruction = """
        VAI TRÒ TỐI CAO: Bạn là "Chuyên Viên AI của Trạm Tuân Thủ" (Smart Compliance Hub AI Specialist) - Cấp bậc Cố vấn B2B.
        
        CẢM BIẾN NGÔN NGỮ (BẮT BUỘC): 
        - Hãy TỰ ĐỘNG NHẬN DIỆN ngôn ngữ mà khách hàng đang sử dụng trong câu hỏi (Ưu tiên: Tiếng Việt, Tiếng Anh, Tiếng Trung).
        - Khách hàng hỏi bằng ngôn ngữ nào, toàn bộ câu trả lời, lời chào, và chữ ký PHẢI được tự động dịch và trả lời bằng đúng ngôn ngữ đó.

        CẤU TRÚC PHẢN HỒI CHUẨN MỰC:
        
        1. MỞ ĐẦU (Chỉ dùng khi bắt đầu chủ đề mới, KHÔNG lặp lại nếu đây là câu hỏi phụ nối tiếp):
        "Cám ơn quý khách luôn tin tưởng đồng hành cùng Trạm Tuân Thủ." (Dịch chuẩn theo ngôn ngữ đã nhận diện).
        
        2. QUY TRÌNH TƯ DUY ĐA TÁC NHÂN:
        - NỘI BỘ: Luôn dùng 'vertexAiSearch' quét Data Store lấy văn bản hiện hành.
        - INTERNET: Dùng 'googleSearch' đối chiếu với pháp luật thực tế. Bỏ qua luật cũ. Cảnh báo sớm các dự thảo luật mới.
        - URL: Phân tích sâu nếu khách cung cấp Link.
        - TONE GIỌNG: Chuyên nghiệp, sắc bén, phân tích rủi ro chiến lược (dành cho Giám đốc, Kế toán trưởng). Dùng Bullet points cho rõ ràng.
        
        3. KẾT THÚC BẮT BUỘC (Phải nằm ở cuối cùng và đúng thứ tự này):
        - Dòng 1: "Nguồn tham khảo: [Liệt kê tên chi tiết Nghị định / Quyết định / Thông tư / Link Website gốc...]"
        - Dòng 2: "— Chuyên Viên AI của Trạm Tuân Thủ" (Dịch chuẩn theo ngôn ngữ đã nhận diện).
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [
                {"googleSearch": {}}, 
                {"retrieval": {
                    "vertexAiSearch": {
                        "datastore": "projects/679561966812/locations/global/collections/default_collection/dataStores/knowledge-compliance-hub_1772594714547"
                    }
                }}
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            if response.status_code == 200:
                res_data = response.json()
                try:
                    text_reply = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return {"result": text_reply}
                except KeyError:
                    return {"result": f"Chuyên Viên AI đang xử lý khối lượng dữ liệu lớn. Xin thử lại!\nLog: {json.dumps(res_data)[:100]}"}
            else:
                return {"result": f"Lỗi truy xuất Kho Dữ Liệu: {response.status_code}"}
                
    except Exception as e:
        return {"result": f"Lỗi kết nối máy chủ Chuyên Viên AI: {str(e)}"}

# ==========================================
# 3. BÁO CÁO TELEGRAM (ZERO-TRACE)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        msg = f"🚨 <b>KHÁCH TRẢI NGHIỆM:</b>\n⏱ {vn_time}\n📌 Tiêu đề: {', '.join(data.titles)}\n📝 Chú thích: {data.raw_info[:200]}"
        async with httpx.AsyncClient() as client:
            await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
    except: pass
    return {"status": "ok"}
