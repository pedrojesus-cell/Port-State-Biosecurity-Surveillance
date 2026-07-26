FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python scripts, configuration, and frontend assets
COPY etl_pipeline.py .
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY assets/ ./assets/

RUN mkdir -p data

CMD ["python", "etl_pipeline.py"]
