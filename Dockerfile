FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY src/ src/
COPY config/ config/
COPY static/ static/

EXPOSE 8000

CMD ["fastapi", "run", "src/blackboard/main.py", "--host", "0.0.0.0", "--port", "8000"]
