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
def read_root(): return {"status": "Online", "version": "v8.1-Auto-Healing-Hooks"}

# ==========================================
# 1. CỖ MÁY MASTER PROMPT SĂN TIN B2B (TỰ ĐỘNG HÓA)
# ==========================================
MASTER_PROMPT = """[ROLE] Bạn là Tổng biên tập Bản tin Doanh nghiệp B2B. 
[MISSION] Tạo 4 Hook (25-40 chữ) về chính sách, kinh tế 24h qua. 
[FORMAT] {"VN": ["✨ Hook 1",...], "EN": [...], "CN": [...]}"""

# Hàm thợ săn chạy ngầm
async def fetch_and_save_hooks_bg():
    if not API_KEYS: return
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[0]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}], "tools": [{"googleSearch": {}}]}
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                hook_data = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"].replace("```json", "").replace("```", "").strip())
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f: 
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Lỗi săn tin ngầm: {e}")

@app.get("/api/generate-hooks")
async def generate_hooks(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return {"status": "success", "message": "Đã phái trinh sát đi săn tin ngầm!"}

@app.get("/api/hooks")
async def get_hooks(background_tasks: BackgroundTasks):
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f: 
            return json.load(f)
    except FileNotFoundError:
        # TỰ ĐỘNG HÓA: Nếu mất trí nhớ, lập tức gọi thợ săn đi lấy tin
        background_tasks.add_task(fetch_and_save_hooks_bg)
        # Trả về câu mồi dự phòng cho khách hàng xem tạm trong 40 giây chờ đợi
        return {
            "VN": ["✨ Trạm Tuân Thủ đang tải tin tức pháp lý thời gian thực...", "✨ Đang phân tích biến động thị trường hôm nay..."],
            "EN": ["✨ Loading real-time legal news...", "✨ Analyzing market fluctuations today..."],
            "CN": ["✨ 正在加载实时法律新闻...", "✨ 正在分析今日市场波动..."]
        }

# ==========================================
# 2. NÃO BỘ LỄ TÂN ĐƯỢC CẤY TRỰC TIẾP VÀO RENDER
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: return {"result": "Lỗi: Chưa cấu hình GCP_JSON_KEY trên Render."}
    
    try:
        # Lấy Token bảo mật từ Google
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        # Gọi thẳng vào siêu trí tuệ Gemini 2.5 Pro trên Vertex AI (Dùng quỹ 33 Triệu)
        project_id = "679561966812"
        location = "us-central1" 
        url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/gemini-2.5-pro:generateContent"
        
        headers = {"Authorization": f"Bearer {scoped_creds.token}", "Content-Type": "application/json"}
        
        system_instruction = f"""
        VAI TRÒ: Đại diện tuyến đầu - Lễ Tân Điều Phối Trạm Tuân Thủ.
        NGÔN NGỮ CHỈ ĐỊNH: Bắt buộc trả lời bằng {req.lang}.
        QUY TRÌNH KÉP:
        1. Ưu tiên tìm kiếm trong Kho Dữ Liệu Nội Bộ (Data Store).
        2. Nếu nội bộ không có, BẮT BUỘC sử dụng công cụ Google Search để cập nhật Luật/Dự thảo từ chinhphu.vn, vbpl.vn.
        3. Kết luận luôn đính kèm Trích dẫn (Nguồn bài viết / Tên Nghị định).
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
