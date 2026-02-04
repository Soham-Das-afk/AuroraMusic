FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# System dependencies for audio (ffmpeg) and general
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the entire project
COPY . .

# Expose the necessary port (if applicable)
# EXPOSE 8080

ENV PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1 \
	PIP_NO_CACHE_DIR=1

# Command to run the bot
CMD ["python", "src/bot.py"]