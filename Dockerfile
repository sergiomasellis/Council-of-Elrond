FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    python-dotenv \
    httpx \
    pydantic

COPY backend/ ./backend/

RUN mkdir -p data/conversations

EXPOSE 8001

CMD ["python", "-m", "backend.main"]
