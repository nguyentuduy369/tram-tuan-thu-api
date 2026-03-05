from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Gọi các "Trưởng phòng" từ 3 file vừa tạo
from float_agent import router as float_router
from workspace_agent import router as workspace_router
from news_hunter import router as news_router

app = FastAPI()

# Mở cửa cho mọi giao diện Web truy cập (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn biển báo, nối đường dẫn vào 3 phòng chuyên biệt
app.include_router(float_router)
app.include_router(workspace_router)
app.include_router(news_router)

# Lời chào của Cổng Chính khi kiểm tra trạng thái máy chủ
@app.get("/")
def read_root():
    return {
        "status": "Online", 
        "version": "v10.0-Modular-Architecture",
        "message": "Trạm Tuân Thủ - Đã phân lô thành công!"
    }
