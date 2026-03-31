# Sử dụng ảnh Python chính thức với hệ điều hành ổn định (Debian 12 Bookworm)
FROM python:3.11-bookworm

# Đặt thư mục làm việc
WORKDIR /app

# Copy file requirements và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt trình duyệt Chromium và các thư viện hệ điều hành cần thiết cho Playwright
RUN playwright install --with-deps chromium

# Copy toàn bộ mã nguồn backend vào container
COPY . .

# Mở cổng 10000 (Cổng mặc định Render thường dùng)
EXPOSE 10000

# Lệnh khởi chạy máy chủ FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]