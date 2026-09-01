# Dockerfile cho Frontend React (Vite)
FROM node:18-alpine

WORKDIR /app

# Copy package files và cài đặt dependencies
COPY frontend/package*.json ./
RUN npm ci

# Copy mã nguồn frontend
COPY frontend/ ./

EXPOSE 5173

# Chạy Vite dev server lắng nghe ở 0.0.0.0
CMD ["sh", "-c", "if [ -f package.json ]; then npm run dev -- --host 0.0.0.0; else tail -f /dev/null; fi"]
