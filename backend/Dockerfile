# Dockerfile cho Backend FastAPI (Tối ưu CPU-only build siêu nhanh)
FROM python:3.11-slim

# Cấu hình môi trường Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Cài đặt các công cụ hệ thống cần thiết
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 🚀 TỐI ƯU SIÊU TỐC: Cài đặt bản PyTorch CPU-only trước (chỉ ~150MB thay vì 4GB CUDA)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Cài đặt các thư viện còn lại từ dependency source of truth
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy mã nguồn backend
COPY backend/ ./backend/
COPY data/ ./data/

EXPOSE 8000

# Chạy FastAPI server bằng Uvicorn
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
