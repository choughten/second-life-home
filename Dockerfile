FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home dashboard
WORKDIR /app
COPY server.py dashboard.html demo.py ./
USER dashboard
EXPOSE 8089
CMD ["python3", "server.py", "--config", "/config/config.json"]
