FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    chromium-browser \
    chromium-chrivedriver \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY uppcl_google_sheets_tracker_v3_6.py .

CMD ["python", "uppcl_google_sheets_tracker_v3_6.py", "--once"]
