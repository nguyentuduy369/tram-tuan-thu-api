import os
import json
import httpx
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException
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

API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GCP_JSON_KEY = os.getenv("GCP_JSON_KEY", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "679561966812")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")
GCP_AGENT_ID = os.getenv("GCP_AGENT_ID", "") 

current_key_idx = 0

@app.get("/")
def read_root(): return {"status": "Online", "version": "v7.1-Agent-Parser-Fixed"}

class ScanRequest(BaseModel):
    query: str
    tool: str = ""

@app.post("/api/scan")
async def scan_document(req: ScanRequest):
    global current_key_idx
    if not API_KEYS: raise HTTPException(status_code=500, detail="Chưa cấu hình API_KEYS!")
    async with httpx.AsyncClient() as client:
        for _ in range(len(API_KEYS)):
            api_key = API_KEYS[current_key_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            try:
                payload = {"contents": [{"parts": [{"text": f"Công cụ: {req.tool}. Hãy phân tích: {req.query}"}]}]}
                response = await client.post(url, json=payload, timeout=30.0)
                if response.status_code == 200: return {"result": response.json()["candidates"][0]["content"]["parts"][0]["text"]}
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            except Exception: current_key_idx = (current_key_idx + 1) % len(API_KEYS)
    raise HTTPException(status_code=429, detail="Google từ chối.")

MASTER_PROMPT = """[ROLE] Bạn là Tổng biên tập Bản tin Doanh nghiệp B2B. 
[MISSION] Tạo 4 Hook (25-40 chữ) về chính sách, kinh tế 24h qua. 
[FORMAT] {"VN": ["✨ Hook 1",...], "EN": [...], "CN": [...]}"""

@app.get("/api/generate-hooks")
async def generate_hooks():
    global current_key_idx
    if not API_KEYS: return {"status": "error"}
    async with httpx.AsyncClient() as client:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEYS[current_key_idx]}"
        try:
            payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}], "tools": [{"googleSearch": {}}]}
            response = await client.post(url, json=payload, timeout=40.0)
            if response.status_code == 200:
                hook_data = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"].replace("```json", "").replace("```", "").strip())
                with open("dynamic_hooks.json", "w", encoding="utf-8") as f: json.dump(hook_data, f, ensure_ascii=False, indent=2)
                current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                return {"status": "success", "data": hook_data}
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error"}
        except Exception:
            current_key_idx = (current_key_idx + 1) % len(API_KEYS)
            return {"status": "error"}

@app.get("/api/hooks")
def get_hooks():
    try:
        with open("dynamic_hooks.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return {"VN": ["✨ Đang tải bản tin pháp lý..."]}

# ==========================================
# 3. KẾT NỐI LÕI LỄ TÂN (ĐÃ NÂNG CẤP RADAR ĐỌC DATA)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    session_id: str
    lang: str = "VN"

@app.post("/api/workspace-chat")
async def workspace_chat(req: ChatRequest):
    if not GCP_JSON_KEY or not GCP_AGENT_ID: return {"result": "Lỗi: Thiếu JSON_KEY hoặc AGENT_ID."}
    try:
        key_dict = json.loads(GCP_JSON_KEY)
        creds = service_account.Credentials.from_service_account_info(key_dict)
        scoped_creds = creds.with_scopes(['https://www.googleapis.com/auth/cloud-platform'])
        scoped_creds.refresh(AuthRequest())
        
        url = f"https://{GCP_LOCATION}-dialogflow.googleapis.com/v3/projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/agents/{GCP_AGENT_ID}/sessions/{req.session_id}:detectIntent"
        headers = {"Authorization": f"Bearer {scoped_creds.token}", "Content-Type": "application/json"}
        lang_code = "en" if req.lang == "EN" else "zh-CN" if req.lang == "CN" else "vi"
        payload = {"queryInput": {"text": {"text": req.query}, "languageCode": lang_code}}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            if response.status_code == 200:
                res_data = response.json()
                messages = res_data.get("queryResult", {}).get("responseMessages", [])
                
                full_reply = ""
                for msg in messages:
                    # Nếu là text bình thường
                    if "text" in msg and "text" in msg["text"]:
                        full_reply += "\n".join(msg["text"]["text"]) + "\n\n"
                    # Nếu là Payload đặc biệt từ Agent Builder
                    elif "payload" in msg:
                        full_reply += f"[Dữ liệu Payload nội bộ: {json.dumps(msg['payload'], ensure_ascii=False)[:150]}...]\n\n"
                
                # Báo động đỏ: Nếu trắng bóc, in raw response ra để debug
                if not full_reply.strip():
                    raw_str = json.dumps(res_data, ensure_ascii=False)
                    return {"result": f"⚠️ [HỆ THỐNG]: Lễ Tân trả về dữ liệu phức tạp chưa đọc được:\n{raw_str[:300]}..."}
                
                return {"result": full_reply.strip()}
            else:
                return {"result": f"Lỗi Agent: {response.status_code} - {response.text}"}
    except Exception as e:
        return {"result": f"Lỗi Server: {str(e)}"}

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
