FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY alert.py .

# Create data directory for persistent state
RUN mkdir data

CMD ["python", "alert.py"]
