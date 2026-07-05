FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Health-check port; container hosts route HTTP probes here.
ENV PORT=7860
EXPOSE 7860

# Long-polling mode: replies within seconds.
CMD ["python", "bot.py", "--loop"]
