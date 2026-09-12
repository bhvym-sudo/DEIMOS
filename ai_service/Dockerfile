FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY ai_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ai_service/ /app/ai_service/
ENV DEIMOS_ROOT=/app
EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=2)" || exit 1
CMD ["python", "-m", "uvicorn", "ai_service.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
