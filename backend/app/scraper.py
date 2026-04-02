import httpx
import asyncio
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NovelScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    async def fetch_html(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=15.0) as client:
                response = await client.get(url)
                
                if response.status_code in (403, 429, 503):
                    logger.warning(f"Bị chặn ở {url} với mã {response.status_code}. Đang kích hoạt Playwright Stealth...")
                    return await self.fetch_html_with_playwright(url)
                
                response.raise_for_status()
                return response.text
                
        except httpx.HTTPError as e:
            logger.warning(f"Lỗi kết nối HTTPX: {e}. Đang thử lại với Playwright...")
            return await self.fetch_html_with_playwright(url)

    async def fetch_html_with_playwright(self, url: str) -> str:
        # Bọc async_playwright() bằng stealth_async() theo chuẩn API 2.0.0
        async with stealth_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=self.headers["User-Agent"])
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                html = await page.content()
                return html
            finally:
                await browser.close()
    def clean_and_extract_chapter(self, html: str, content_selector: str = "div.chapter-c", title_selector: str = "a.chapter-title") -> dict:
        soup = BeautifulSoup(html, "html.parser")
        
        title_tag = soup.select_one(title_selector)
        title = title_tag.text.strip() if title_tag else "Chương Không Tên"
        
        content_div = soup.select_one(content_selector)
        
        if not content_div:
            return {"title": title, "content": "<p>Lỗi: Không tìm thấy nội dung chương.</p>"}
        
        for tag in content_div(["script", "style", "iframe", "noscript"]):
            tag.decompose()
            
        for p in content_div.find_all("p"):
            if "Bạn đang đọc truyện tại" in p.text:
                p.decompose()
                
        return {
            "title": title,
            "content": str(content_div)
        }