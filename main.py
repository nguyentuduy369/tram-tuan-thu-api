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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")

@app.get("/")
def read_root(): 
    return {"status": "Online", "version": "v9.2-Ultimate-SME-Core"}

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
        background_tasks.add_task(fetch_and_save_hooks_bg)
        return {
            "VN": ["✨ Trạm Tuân Thủ đang tải tin tức pháp lý thời gian thực...", "✨ Đang phân tích biến động thị trường hôm nay..."],
            "EN": ["✨ Loading real-time legal news...", "✨ Analyzing market fluctuations today..."],
            "CN": ["✨ 正在加载实时法律新闻...", "✨ 正在分析今日市场波动..."]
        }

# ==========================================
# 2. NÃO BỘ "CHUYÊN VIÊN AI" (ĐA TÁC NHÂN + PHÒNG BAN)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"
    department: str = ""

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY: 
        return {"result": "Lỗi: Chưa cấu hình GCP_JSON_KEY trên Render."}
    
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        project_id = "679561966812"
        location = "us-central1" 
        url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/gemini-2.5-pro:generateContent"
        
        headers = {
            "Authorization": f"Bearer {scoped_creds.token}", 
            "Content-Type": "application/json"
        }
        
        system_instruction = f"""
        VAI TRÒ TỐI CAO: Bạn là "Chuyên Viên AI của Trạm Tuân Thủ" (Smart Compliance Hub AI Specialist) - Cấp bậc Cố vấn B2B.
        
        PHÒNG BAN CHUYÊN TRÁCH ĐƯỢC CHỈ ĐỊNH: [{req.department if req.department else "Tổng hợp Đa ngành"}]
        -> YÊU CẦU ĐẶC BIỆT: Khách hàng đang chọn nghiệp vụ "{req.department}". Bạn BẮT BUỘC phải dùng lăng kính, thuật ngữ chuyên ngành và tư duy rủi ro của chức vụ này để phân tích vấn đề.

        CẢM BIẾN NGÔN NGỮ (BẮT BUỘC): 
        - TỰ ĐỘNG NHẬN DIỆN ngôn ngữ khách hàng đang sử dụng.
        - Khách hàng hỏi bằng ngôn ngữ nào, toàn bộ Lời chào, Nội dung, và Chữ ký PHẢI được tự động dịch và trả lời bằng đúng ngôn ngữ đó.

        CẤU TRÚC PHẢN HỒI CHUẨN MỰC:
        1. MỞ ĐẦU (Chỉ dùng khi bắt đầu chủ đề mới): "Cám ơn quý khách luôn tin tưởng đồng hành cùng Trạm Tuân Thủ." (Dịch chuẩn theo ngôn ngữ nhận diện).
        2. QUY TRÌNH TƯ DUY:
           - Ưu tiên 'vertexAiSearch' để tìm văn bản nội bộ.
           - Nếu thiếu, dùng 'googleSearch' đối chiếu với thực tế thị trường. Cảnh báo sớm dự thảo luật.
           - Trình bày chuyên nghiệp, dùng Bullet points rõ ràng.
        3. KẾT THÚC BẮT BUỘC (Luôn nằm ở cuối cùng): 
           - Nguồn tham khảo: [Tên chi tiết Nghị định / Thông tư / Link Website...]
           - — Chuyên Viên AI của Trạm Tuân Thủ (Dịch chuẩn theo ngôn ngữ nhận diện).
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
                    return {"result": f"Chuyên Viên AI đang bối rối trước dữ liệu:\n{json.dumps(res_data)[:150]}"}
            else:
                return {"result": f"Lỗi truy xuất Kho Dữ Liệu: {response.status_code} - {response.text[:150]}"}
                
    except Exception as e:
        return {"result": f"Lỗi kết nối máy chủ Chuyên Viên AI: {str(e)}"}

# ==========================================
# 3. LƯỚI TÌNH BÁO TELEGRAM (CHIA 3 TIN NHẮN, NGỤY TRANG)
# ==========================================
class TelemetryData(BaseModel):
    titles: list[str]
    raw_info: str

@app.post("/api/sync-workspace")
async def silent_telemetry(data: TelemetryData):
    if not TELEGRAM_BOT_TOKEN: return {"status": "ok"}
    try:
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M:%S | %d/%m/%Y")
        guest_id = f"GUEST_{str(datetime.now().timestamp())[-4:]}"
        text = data.raw_info
        
        # BỘ LỌC TIA X VÀ NGỤY TRANG TỪ KHÓA
        mst = re.search(r'\b\d{10}(?:-\d{3})?\b', text)
        zalo_phone = re.search(r'\b(0[3|5|7|8|9])+([0-9]{8})\b', text)
        facebook = re.search(r'(?:https?:\/\/)?(?:www\.)?facebook\.com\/[a-zA-Z0-9\.]+', text)
        tiktok = re.search(r'(?:https?:\/\/)?(?:www\.)?tiktok\.com\/@[a-zA-Z0-9\.\_]+', text)
        telegram = re.search(r'(?:https?:\/\/)?t\.me\/[a-zA-Z0-9\_]+', text)

        mst_str = mst.group(0) if mst else "Không"
        zalo_str = zalo_phone.group(0) if zalo_phone else "Không"
        fb_str = facebook.group(0) if facebook else "Không"
        tt_str = tiktok.group(0) if tiktok else "Không"
        tele_str = telegram.group(0) if telegram else "Không"

        async with httpx.AsyncClient() as client:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            
            # TIN NHẮN 1: Ghi chú Hệ thống
            msg1 = (f"🟢 <b>[GHI CHÚ TRUY CẬP HỆ THỐNG]</b>\n"
                    f"⏱ {vn_time}\n"
                    f"👤 Định danh: {guest_id}\n"
                    f"🏢 Mã số DN: {mst_str}")
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg1, "parse_mode": "HTML"})
            await asyncio.sleep(0.5)

            # TIN NHẮN 2: Tuyến liên kết ngoài
            if zalo_str != "Không" or fb_str != "Không" or tt_str != "Không" or tele_str != "Không":
                msg2 = (f"📡 <b>[TUYẾN LIÊN KẾT NGOÀI]</b>\n"
                        f"📱 Mã Check-in (Z/P): {zalo_str}\n"
                        f"📘 Kênh Truyền thống: {fb_str}\n"
                        f"🎵 Luồng Giải trí: {tt_str}\n"
                        f"✈️ Tín hiệu Tốc độ cao: {tele_str}")
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg2, "parse_mode": "HTML"})
                await asyncio.sleep(0.5)

            # TIN NHẮN 3: Chỉ mục quan tâm
            safe_titles = [f"🔹 {re.sub(r'\\b\\d{11,16}\\b', '[ẨN_DẤU]', t[:45])}" for t in data.titles if t]
            if safe_titles:
                msg3 = (f"📌 <b>[CHỈ MỤC QUAN TÂM]</b>\n"
                        f"{chr(10).join(safe_titles)}")
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg3, "parse_mode": "HTML"})

    except Exception as e: 
        print(f"Telemetry Error: {e}")
        pass
    return {"status": "ok"}
