FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py chat.py chunking.py embeddings.py ./

EXPOSE 5001

# --preload imports the app once, so tables are created only once.
# --timeout 90 leaves room for slow AI model calls.
CMD ["gunicorn", "--preload", "-w", "2", "--timeout", "90", "-b", "0.0.0.0:5001", "app:app"]
