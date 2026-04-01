import os
import asyncio
import gc
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

from app.scraper import NovelScraper
from app.epub_builder import EpubBuilder

app = FastAPI(title="ePub Scraper Queue API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Khởi tạo Supabase Client
SUPABASE_URL = os.environ.get("SUPABASE_URL", "MÃ_URL_CỦA_BẠN")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "MÃ_KEY_CỦA_BẠN")
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Lỗi khởi tạo Supabase: {e}")
    supabase = None

# 2. Cấu hình Email (SMTP)
conf = ConnectionConfig(
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "email_cua_ban@gmail.com"),
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "mat_khau_ung_dung"),
    MAIL_FROM = os.environ.get("MAIL_USERNAME", "email_cua_ban@gmail.com"),
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

class JobRequest(BaseModel):
    url: str
    title: str
    chapter_range: str # VD: "1-100"
    email: EmailStr

@app.post("/api/v1/scraper/jobs", status_code=202)
async def create_job(request: JobRequest):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase chưa được cấu hình.")
        
    # Quy tắc: 1 email chỉ có 1 request đang chạy hoặc chờ
    active_jobs = supabase.table("jobs").select("*").eq("email", request.email).in_("status", ["pending", "running"]).execute()
    if len(active_jobs.data) > 0:
        raise HTTPException(status_code=429, detail="Email này đang có 1 yêu cầu chưa hoàn tất. Vui lòng chờ!")
    
    # Thêm tác vụ vào hàng đợi Supabase
    new_job = {
        "email": request.email,
        "url": request.url,
        "title": request.title,
        "chapter_range": request.chapter_range,
        "status": "pending"
    }
    res = supabase.table("jobs").insert(new_job).execute()
    return {"job_id": res.data["id"], "message": "Đã thêm vào hàng đợi thành công."}

@app.get("/api/v1/scraper/jobs/{job_id}")
async def get_job_status(job_id: str):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase chưa được cấu hình.")
        
    res = supabase.table("jobs").select("status, progress, message").eq("id", job_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình.")
    return res.data

# --- VÒNG LẶP CHẠY NGẦM ĐỂ XỬ LÝ HÀNG ĐỢI ---
async def background_worker():
    if not supabase:
        return
        
    while True:
        try:
            # Lấy 1 tác vụ cũ nhất đang ở trạng thái 'pending'
            pending_jobs = supabase.table("jobs").select("*").eq("status", "pending").order("created_at").limit(1).execute()
            
            if pending_jobs.data:
                job = pending_jobs.data
                job_id = job["id"]
                
                # Khóa tác vụ (đổi sang running)
                supabase.table("jobs").update({"status": "running", "message": "Đang xử lý..."}).eq("id", job_id).execute()
                
                try:
                    # Phân tích khoảng chương (VD: "101-200")
                    start_chap, end_chap = map(int, job["chapter_range"].split("-"))
                    total_chapters = end_chap - start_chap + 1
                    
                    scraper = NovelScraper()
                    book_title = f"{job['title']} (Chương {start_chap}-{end_chap})"
                    builder = EpubBuilder(title=book_title)
                    
                    # Tự động nhận diện và thêm https:// nếu URL bị thiếu
                    base_url = job["url"] if job["url"].startswith("http") else f"https://{job['url']}"
                    
                    # Cấu hình CSS Selector linh hoạt
                    if "tramtruyen.vip" in base_url:
                        content_sel = "#chapter-content"
                        title_sel = "#chapter-content p:first-of-type"
                    else:
                        content_sel = "div.chapter-c"
                        title_sel = "a.chapter-title"
                        
                    chapter_urls = [f"{base_url}/chuong-{i}" for i in range(start_chap, end_chap + 1)]
                    
                    for index, chap_url in enumerate(chapter_urls):
                        progress = int(((index + 1) / total_chapters) * 100)
                        msg = f"Đang tải chương {start_chap + index} ({index + 1}/{total_chapters})"
                        supabase.table("jobs").update({"progress": progress, "message": msg}).eq("id", job_id).execute()
                        
                        html = await scraper.fetch_html(chap_url)
                        extracted = scraper.clean_and_extract_chapter(html, content_selector=content_sel, title_selector=title_sel)
                        builder.add_chapter(extracted["title"], extracted["content"], index + 1)
                        
                        await asyncio.sleep(1)
                        if (index + 1) % 5 == 0:
                            gc.collect()
                    
                    supabase.table("jobs").update({"message": "Đang đóng gói và gửi Email..."}).eq("id", job_id).execute()
                    
                    os.makedirs("downloads", exist_ok=True)
                    output_file = f"downloads/{job_id}.epub"
                    builder.build(output_file)
                    
                    # Gửi file ePub qua Email
                    message = MessageSchema(
                        subject=f"Tệp ePub của bạn: {book_title}",
                        recipients=[job["email"]],
                        body=f"Xin chào,\n\nQuá trình tải {book_title} đã hoàn tất. Tệp ePub của bạn được đính kèm trong email này.\n\nChúc bạn đọc truyện vui vẻ!",
                        subtype=MessageType.plain,
                        attachments=[output_file]
                    )
                    fm = FastMail(conf)
                    await fm.send_message(message)
                    
                    # Dọn rác file sau khi gửi
                    if os.path.exists(output_file):
                        os.remove(output_file) 
                        
                    supabase.table("jobs").update({"status": "completed", "progress": 100, "message": "Đã gửi tệp qua Email thành công!"}).eq("id", job_id).execute()
                    
                except Exception as e:
                    supabase.table("jobs").update({"status": "failed", "message": f"Lỗi: {str(e)}"}).eq("id", job_id).execute()
                    
        except Exception as err:
            print(f"Lỗi worker: {err}")
            pass # Bỏ qua lỗi mất kết nối DB tạm thời
        
        await asyncio.sleep(5) # Nghỉ 5s trước khi quét tác vụ tiếp theo

@app.on_event("startup")
async def startup_event():
    # Khởi động worker ngay khi máy chủ API chạy
    asyncio.create_task(background_worker())