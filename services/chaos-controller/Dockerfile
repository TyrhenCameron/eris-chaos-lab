FROM python:3.11-slim

WORKDIR /app

# installing docker cli to get control to other containers inside this container
RUN apt-gret update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0,0,0,0", "--port", "8080"]
