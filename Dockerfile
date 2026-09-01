FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src /app/src
COPY examples /app/examples
COPY web /app/web

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .[dev]

ENV PYTHONPATH=/app/src
CMD ["python", "-m", "research_agent.cli", "--help"]
