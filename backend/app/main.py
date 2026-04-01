from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import os
import asyncio
import gc

from app.scraper import NovelScraper
from app.epub_builder import EpubBuilder

app = FastAPI(title="ePub Scraper API", version="1.0")

# BỔ SUNG CẤU HÌNH CORS TẠI ĐÂY ĐỂ VERCEL CÓ THỂ GỌI API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các tên miền gọi tới API
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các phương thức (GET, POST, OPTIONS)
    allow_headers=["*"],  # Cho phép tất cả các headers
)

jobs = {}

class ScrapeRequest(BaseModel):
    url: str
    title: str
    author: str = "Unknown"
    max_chapters: int = 100

async def process_novel_task(job_id: str, request: ScrapeRequest):
    jobs[job_id] = {"status": "running", "progress": 0, "message": "Đang khởi tạo...", "file_path": None, "title": request.title}
    scraper = NovelScraper()
    builder = EpubBuilder(title=request.title, author=request.author)
    
    try:
        # Tự động nhận diện và thêm https:// nếu URL bị thiếu
        base_url = request.url if request.url.startswith("http") else f"https://{request.url}"
        
        jobs[job_id]["message"] = f"Đang phân tích URL truyện: {base_url}"
        await asyncio.sleep(1) 
        
        # --- BỔ SUNG LOGIC NHẬN DIỆN TRANG WEB ĐỂ DÙNG ĐÚNG CSS SELECTOR ---
        if "tramtruyen.vip" in base_url:
            content_sel = "#chapter-content"
            title_sel = "#chapter-content p:first-of-type"
        else:
            content_sel = "div.chapter-c"
            title_sel = "a.chapter-title"
        # ------------------------------------------------------------------

        # Sử dụng base_url thay vì request.url
        chapter_urls = [f"{base_url}/chuong-{i}" for i in range(1, request.max_chapters + 1)]
        total_chapters = len(chapter_urls)
        
        for index, chap_url in enumerate(chapter_urls):
            jobs[job_id]["message"] = f"Đang tải chương {index + 1}/{total_chapters}"
            
            html = await scraper.fetch_html(chap_url)
            
            # Truyền bộ chọn CSS linh hoạt vào hàm làm sạch
            extracted_data = scraper.clean_and_extract_chapter(
                html, 
                content_selector=content_sel, 
                title_selector=title_sel
            )
            
            builder.add_chapter(
                title=extracted_data["title"], 
                content=extracted_data["content"], 
                chapter_index=index + 1
            )
            
            jobs[job_id]["progress"] = int(((index + 1) / total_chapters) * 100)
            
            # Tối ưu bộ nhớ: dừng 1 giây và dọn rác mỗi 5 chương để tránh quá tải RAM
            await asyncio.sleep(1)
            if (index + 1) % 5 == 0:
                gc.collect()
            
        jobs[job_id]["message"] = "Đang đóng gói và biên dịch tệp ePub..."
        os.makedirs("downloads", exist_ok=True)
        output_file_path = f"downloads/{job_id}.epub"
        
        builder.build(output_file_path)
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Hoàn thành!"
        jobs[job_id]["file_path"] = output_file_path

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Lỗi hệ thống: {str(e)}"


@app.post("/api/v1/scraper/jobs", status_code=202)
async def start_scraping_job(request: ScrapeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_novel_task, job_id, request)
    return {"job_id": job_id, "message": "Tiến trình thu thập đã bắt đầu chạy ngầm."}


@app.get("/api/v1/scraper/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình.")
    return jobs[job_id]


@app.get("/api/v1/ebooks/{job_id}/download")
async def download_generated_epub(job_id: str):
    if job_id not in jobs or jobs[job_id].get("status")!= "completed":
        raise HTTPException(status_code=400, detail="Tệp sách chưa sẵn sàng.")
    
    file_path = jobs[job_id]["file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Tệp không tồn tại.")
        
    return FileResponse(
        path=file_path, 
        filename=f"{jobs[job_id].get('title', 'truyen_chu')}.epub", 
        media_type="application/epub+zip"
    )