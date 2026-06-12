FROM python:3.11-slim

# Установка ffmpeg для конвертации аудио
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папку для загрузок
RUN mkdir -p downloads

CMD ["python", "bot.py"]