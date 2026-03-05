import os
import json
import httpx
import re
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, BackgroundTasks
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

# === KÉT SẮT BẢO MẬT TỪ RENDER ===
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")

# Bot 1: Tình báo ngầm (Workspace)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Bot 2: Giám sát Tiểu Khả Ái (Float Assistant)
FLOAT_TELEGRAM_TOKEN = os.getenv("FLOAT_TELEGRAM_TOKEN", TELEGRAM_BOT_TOKEN) # Nếu chưa cài, mượn tạm Bot 1
FLOAT_TELEGRAM_CHAT_ID = os.getenv("FLOAT_TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)

@app.get("/")
def read_root(): 
    return {"status": "Online", "version": "v9.4-Xiao-Ke-Ai-Admin-Mirror"}

# ==========================================
# 1. CỖ MÁY MASTER PROMPT SĂN TIN B2B (TỰ CHỮA LÀNH)
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
                raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                clean_json = raw_text.replace("```json", "").replace("```", "").strip()
                hook_data = json.loads(clean_json)
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f: 
                    json.dump(hook_data, f, ensure_ascii=False, indent=2)
        except Exception as e: pass

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
        return {"VN": ["✨ Đang tải tin tức pháp lý thời gian thực..."], "EN": ["✨ Loading real-time news..."], "CN": ["✨ 正在加载新闻..."]}

# ==========================================
# 2. NÃO BỘ "CHUYÊN VIÊN AI" (DÀNH CHO HERO WORKSPACE)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"
    department: str = ""

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: return {"result": "Lỗi: Chưa cấu hình GCP_JSON_KEY."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        system_instruction = f"""
        VAI TRÒ TỐI CAO: "Chuyên Viên AI của Trạm Tuân Thủ" - Cấp bậc Cố vấn B2B.
        PHÒNG BAN CHUYÊN TRÁCH: [{req.department if req.department else "Tổng hợp Đa ngành"}]
        YÊU CẦU: Phân tích vấn đề bằng thuật ngữ chuyên ngành {req.department}. Trả lời bằng {req.lang}. Ưu tiên tìm trong 'vertexAiSearch'.
        KẾT THÚC BẮT BUỘC: Nguồn tham khảo: [...] — Chuyên Viên AI của Trạm Tuân Thủ.
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [{"googleSearch": {}}, {"retrieval": {"vertexAiSearch": {"datastore": "projects/679561966812/locations/global/collections/default_collection/dataStores/knowledge-compliance-hub_1772594714547"}}}]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}, timeout=60.0)
            if response.status_code == 200:
                return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
            else:
                return {"result": f"Lỗi truy xuất Kho Dữ Liệu: {response.status_code}"}
    except Exception as e:
        return {"result": f"Lỗi kết nối máy chủ: {str(e)}"}

# ==========================================
# 3. TRỢ LÝ TIỂU KHẢ ÁI (DÀNH CHO FLOAT ASSISTANT)
# ==========================================
class FloatRequest(BaseModel):
    query: str
    lang: str = "VN"
    user_name: str = "" # Đã thêm dây thần kinh nhận tên
    user_job: str = ""  # Đã thêm dây thần kinh nhận chức vụ

@app.post("/api/float-chat")
async def float_chat(req: FloatRequest):
    if not GCP_JSON_KEY: return {"result": "Hệ thống đang bảo trì..."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict).with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        creds.refresh(AuthRequest())
        
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/679561966812/locations/us-central1/publishers/google/models/gemini-2.5-pro:generateContent"
        
        # MASTER PROMPT CÁ NHÂN HÓA 100%
        system_instruction = f"""
        VAI TRÒ: Bạn là "Tiểu Khả Ái", nữ trợ lý AI thông minh, duyên dáng và thấu cảm của Trạm Tuân Thủ.
        KHÁCH HÀNG HIỆN TẠI: Tên là "{req.user_name}", Chức vụ/Công việc: "{req.user_job}".
        
        CHIẾN THUẬT GIAO TIẾP:
        - Xưng hô là "Tiểu Khả Ái" (hoặc "em") và gọi khách hàng bằng [Chức vụ + Tên] (Ví dụ: "Dạ, thưa Giám đốc Tuấn...", "Dạ, thưa Kế toán Lan...").
        - Lắng nghe nỗi đau của doanh nghiệp. Tạo cảm giác an toàn, kín đáo.
        - Khéo léo đề xuất: "Để đảm bảo bảo mật và hỗ trợ sâu hơn, {req.user_name} có tiện trao đổi qua Zalo hay Telegram riêng với chuyên gia cấp cao bên em không ạ?"
        - Trả lời bằng ngôn ngữ {req.lang}. KHÔNG viện dẫn luật dài dòng, hãy tâm sự chuyên nghiệp.
        """

        payload = {
            "contents": [{"role": "user", "parts": [{"text": req.query}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "tools": [{"googleSearch": {}}] 
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}, timeout=60.0)
            text_reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            
            # GƯƠNG PHẢN CHIẾU: Báo cáo cho Nhóm Admin Telegram
            if FLOAT_TELEGRAM_TOKEN:
                vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M")
                msg = (f"🌸 <b>[TIỂU KHẢ ÁI - ĐANG TƯ VẤN]</b>\n"
                       f"⏱ {vn_time}\n"
                       f"👤 Khách: <b>{req.user_job} {req.user_name}</b>\n"
                       f"💬 Hỏi: <i>{req.query[:150]}</i>\n"
                       f"🤖 Trả lời: {text_reply[:150]}...")
                await client.post(f"https://api.telegram.org/bot{FLOAT_TELEGRAM_TOKEN}/sendMessage", json={"chat_id": FLOAT_TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
            
            return {"result": text_reply}
    except Exception as e:
        return {"result": "Dạ mạng hơi yếu, anh/chị nói lại giúp Tiểu Khả Ái được không ạ..."}

# ==========================================
# 4. LƯỚI TÌNH BÁO (ZERO-TRACE WORKSPACE)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S")
        mst = re.search(r'\b\d{10}(?:-\d{3})?\b', data.raw_info)
        mst_str = mst.group(0) if mst else "Không"

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            msg1 = f"🟢 <b>[GHI CHÚ TRUY CẬP]</b>\n⏱ {vn_time}\n🏢 Mã số DN: {mst_str}"
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg1, "parse_mode": "HTML"})
            
            safe_titles = [f"🔹 {t[:45]}" for t in data.titles if t]
            if safe_titles:
                msg3 = f"📌 <b>[CHỈ MỤC QUAN TÂM]</b>\n{chr(10).join(safe_titles)}"
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg3, "parse_mode": "HTML"})
    except Exception: pass
    return {"status": "ok"}
