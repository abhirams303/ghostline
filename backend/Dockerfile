FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY data ./data

RUN pip install --no-cache-dir .

EXPOSE 80

CMD ["fastapi", "run", "app/main.py", "--port", "80"]
