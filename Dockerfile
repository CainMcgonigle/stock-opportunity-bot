FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Ensure log and state files exist for volume mounts
RUN touch seen_articles.json bot.log

CMD ["python", "main.py"]
