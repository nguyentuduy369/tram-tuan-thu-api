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
def read_root(): return {"status": "Online", "version": "v8.2-Multi-Agent-Architect"}

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
# 2. NÃO BỘ LỄ TÂN (HỢP NHẤT 3 CHUYÊN GIA)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"

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
        
        # BỘ LUẬT TỐI CAO CỦA GIÁM ĐỐC TRUYỀN VÀO AI
        system_instruction = f"""
        VAI TRÒ TỐI CAO: Bạn là hệ thống trí tuệ nhân tạo chuyên sâu "Trạm Tuân Thủ" (Smart Compliance Hub).
        NGÔN NGỮ BẮT BUỘC: Phải trả lời hoàn toàn bằng ngôn ngữ {req.lang} (Nếu người dùng dùng tiếng Anh, trả lời tiếng Anh; tiếng Trung trả lời tiếng Trung).
        
        LỜI CHÀO MỞ ĐẦU BẮT BUỘC: "Thư ký Trạm Tuân Thủ xin kính chào quý khách. Dưới đây là báo cáo phân tích:" (Hãy dịch lời chào này sang ngôn ngữ {req.lang}).
        
        QUY TRÌNH TƯ DUY ĐA TÁC NHÂN (Hoạt động như 3 chuyên gia):
        
        1. CHUYÊN GIA NỘI BỘ (Ưu tiên số 1): 
        - BẮT BUỘC dùng công cụ 'vertexAiSearch' để lục lọi trong Data Store nội bộ trước. Đây là nguồn chân lý chứa văn bản hiện hành (Thông tư, Nghị định, Dự thảo của Chính phủ).
        
        2. CHUYÊN GIA INTERNET (Kích hoạt khi nội bộ thiếu dữ liệu):
        - Tự động dùng 'googleSearch' để tìm kiếm. Đóng vai Pháp chế/Luật sư doanh nghiệp/Kiểm toán viên.
        - NGHIÊM CẤM viện dẫn văn bản hết hiệu lực. PHẢI cảnh báo sớm các dự thảo/thông tư sắp áp dụng.
        - BẮT BUỘC cung cấp link gốc (chinhphu.vn, vbpl.vn, mof.gov.vn...) hoặc link PDF khi trích dẫn Luật.
        - Đọc vị khách hàng: Luôn đưa ra câu trả lời mang tầm nhìn chiến lược, tư vấn rủi ro chuyên sâu vì khách hàng của bạn là Giám đốc, Kế toán trưởng, Thanh tra.
        
        3. CHUYÊN GIA URL:
        - Nếu khách hàng cung cấp đường link (URL) trong câu hỏi, hãy lập tức đọc hiểu nội dung URL đó, đối chiếu với luật lệ hiện hành và báo cáo chuyên nghiệp.
        
        QUY TẮC TRÌNH BÀY:
        - Văn phong B2B cực kỳ chuyên nghiệp, sắc bén, phân chia rõ các ý (dùng Bullet points).
        - KẾT LUẬN BẮT BUỘC Ở CUỐI: Luôn kết thúc bằng câu "Nguồn: [Tên các tài liệu / Link trích dẫn] — Tổng hợp bởi Trạm Tuân Thủ (Smart Compliance Hub)." (Dịch sang ngôn ngữ {req.lang}).
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [
                {"googleSearch": {}}, # Vũ khí cho Chuyên gia Internet
                {"retrieval": {
                    "vertexAiSearch": { # Vũ khí cho Chuyên gia Nội bộ
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
                    return {"result": f"Lễ Tân đang bối rối trước dữ liệu:\n{json.dumps(res_data)[:200]}"}
            else:
                return {"result": f"Lỗi truy xuất Kho Dữ Liệu: {response.status_code} - {response.text[:200]}"}
                
    except Exception as e:
        return {"result": f"Lỗi hệ thống thần kinh Lễ Tân: {str(e)}"}

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
