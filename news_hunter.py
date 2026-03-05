import os
import json
import httpx
from fastapi import APIRouter, BackgroundTasks

router = APIRouter()

# ĐỘNG CƠ 1: Dàn 9 API Keys miễn phí (Luân phiên sử dụng)
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]

# MASTER PROMPT CHO TRINH SÁT (Tập trung sâu vào nỗi đau SME)
MASTER_PROMPT = """[ROLE] Bạn là Chuyên gia Copywriter B2B và Cố vấn Pháp lý Doanh nghiệp hàng đầu tại Việt Nam.
[MISSION] Tạo 8 đến 12 câu Hook (Câu dẫn chuyện) cực kỳ hấp dẫn về tin tức nóng, dự thảo pháp lý, thuế, kế toán, M&A, hoặc quản trị SME.
[RULES] 
- BẮT BUỘC mỗi Hook phải có độ dài từ 25 đến 40 CHỮ (Words).
- Văn phong: Mang tính cảnh báo rủi ro, hé lộ cơ hội hoặc "chạm" đúng nỗi đau của chủ doanh nghiệp, thôi thúc họ muốn tìm hiểu ngay.
- Nội dung thực tế: Dựa trên bối cảnh pháp lý, kinh tế vĩ mô của Việt Nam hiện hành.
[FORMAT] Bắt buộc xuất ra JSON thuần túy, không có định dạng markdown:
{"VN": ["Hook 1...", "Hook 2..."], "EN": ["..."], "CN": ["..."]}"""

# KHO ĐẠN DỰ PHÒNG (RAM CACHE): Nạp sẵn 8 câu Hook sát thủ
memory_hooks = {
    "VN": [
        "Dự thảo thuế TNDN mới nhất: Hàng loạt chi phí có thể bị loại trừ nếu doanh nghiệp SME không chuẩn bị bộ chứng từ hợp lệ ngay từ hôm nay.",
        "Báo động đỏ kế toán: Cơ quan thuế siết chặt kiểm tra hóa đơn điện tử, hàng ngàn doanh nghiệp đối mặt án phạt vì đối tác bỏ trốn khỏi địa chỉ.",
        "Làn sóng M&A bùng nổ: Cơ hội vàng để các doanh nghiệp nhỏ huy động vốn, nhưng rủi ro pháp lý tiềm ẩn có thể khiến bạn mất trắng cơ ngơi.",
        "Bảo hiểm xã hội bắt buộc: Tối ưu hóa quỹ lương hợp pháp đang là bài toán sinh tử để giữ chân nhân tài mà không làm cạn kiệt dòng tiền.",
        "Luật Đất đai sửa đổi: Doanh nghiệp sản xuất cần chú ý ngay đến biến động giá thuê đất khu công nghiệp để không bị đội chi phí vận hành lên gấp đôi.",
        "Thanh tra lao động: 5 lỗi sai cơ bản trong hợp đồng lao động khiến doanh nghiệp bồi thường hàng trăm triệu đồng cho nhân viên nghỉ việc trái luật.",
        "Giải mã bài toán vốn: Lãi suất vay B2B đang ở mức có nhiều biến động, đây là lúc rà soát lại hợp đồng tín dụng và tái cấu trúc nợ.",
        "Khủng hoảng vi phạm bản quyền: Chỉ một hình ảnh tải trên mạng hoặc dùng phần mềm lậu cũng đủ để công ty bạn dính kiện tụng và phong tỏa tài khoản."
    ],
    "EN": [
        "Latest CIT draft: Many expenses may be excluded if SMEs do not prepare valid documentation starting today to ensure full legal compliance.",
        "Accounting red alert: Tax authorities tighten e-invoice checks, thousands face penalties due to absconding business partners and invalid invoices.",
        "M&A wave booming: Golden chance for small businesses to raise capital, but hidden legal risks could cost you your entire enterprise.",
        "Mandatory social insurance: Legally optimizing payroll funds is vital to retain top talent without draining your company's cash flow.",
        "Revised Land Law: Manufacturing firms must note industrial zone rent fluctuations immediately to avoid doubling their operational costs.",
        "Labor inspections: 5 common errors in labor contracts that force companies to pay hundreds of millions in compensation for illegal dismissals.",
        "Decoding capital: B2B loan interest rates are fluctuating; now is the critical time to review credit contracts and restructure corporate debt.",
        "Copyright crisis: A single downloaded image or pirated software is enough to embroil your company in lawsuits and freeze bank accounts."
    ],
    "CN": [
        "最新企业所得税草案：如果中小企业不从今天开始准备有效的证明文件，大量费用可能会被排除在税前扣除之外。",
        "会计红色警报：税务机关加强电子发票检查，数千家企业因合作伙伴逃跑和发票无效而面临严厉处罚。",
        "并购浪潮爆发：小企业筹集资金的黄金机会，但隐藏的法律风险可能会让您失去整个辛苦建立的基业。",
        "强制性社会保险：合法优化工资基金是留住顶尖人才而不耗尽公司现金流的生死攸关的难题。",
        "修订后的土地法：制造企业必须立即注意工业区租金的波动，以免将日常运营成本增加一倍以上。",
        "劳工检查：劳动合同中的5个常见错误导致公司因非法解雇员工而支付数亿越南盾的巨额赔偿金。",
        "解码资金难题：B2B贷款利率正在波动；现在是审查信贷合同和重组企业债务的关键时刻。",
        "版权危机：一张在网络上下载的图片或盗版软件足以让您的公司卷入诉讼并被冻结所有银行账户。"
    ]
}

async def fetch_and_save_hooks_bg():
    global memory_hooks
    if not API_KEYS: return
    
    # Sử dụng Key đầu tiên (Nếu có cơ chế xoay vòng sẽ phức tạp, tạm dùng Key 0)
    api_key = API_KEYS[0]
    
    payload = {"contents": [{"parts": [{"text": MASTER_PROMPT}]}]}
    
    async with httpx.AsyncClient() as client:
        # CHIẾN THUẬT: Động cơ Kép (Pro -> Flash)
        url_pro = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}"
        url_flash = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        try:
            # Bước 1: Gọi mô hình Pro (Chất lượng cao, tư duy sâu)
            response = await client.post(url_pro, json=payload, timeout=60.0)
            if response.status_code != 200:
                raise ValueError("Pro failed or rate limited")
        except Exception:
            try:
                # Bước 2: Dự phòng gọi mô hình Flash (Nhanh, nhẹ, chữa cháy)
                response = await client.post(url_flash, json=payload, timeout=40.0)
                if response.status_code != 200:
                    return # Thất bại toàn tập -> Dừng lại, giữ nguyên kho đạn cũ trong RAM
            except Exception:
                return 
                
        # Nếu gọi API thành công (bằng 1 trong 2 mô hình)
        try:
            raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            new_hooks = json.loads(clean_json)
            
            # Kiểm tra định dạng xem AI có trả về đúng Cấu trúc không
            if "VN" in new_hooks and isinstance(new_hooks["VN"], list) and len(new_hooks["VN"]) >= 8:
                memory_hooks = new_hooks # Cập nhật RAM bằng đạn mới
        except Exception:
            pass # AI trả lời tào lao -> Bỏ qua, xài đạn cũ

@router.get("/api/generate-hooks")
async def generate_hooks(background_tasks: BackgroundTasks):
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return {"status": "success"}

@router.get("/api/hooks")
async def get_hooks(background_tasks: BackgroundTasks):
    global memory_hooks
    # Trả về ngay lập tức nội dung từ RAM (0 giây delay)
    # Đồng thời phái Trinh sát chạy ngầm đi cập nhật tin mới cho đợt sau
    background_tasks.add_task(fetch_and_save_hooks_bg)
    return memory_hooks
