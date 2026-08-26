FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir "opentelemetry-proto>=1.44.0"

COPY traffic_generator.py .

CMD ["python", "traffic_generator.py"]
