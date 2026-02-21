FROM python:3.11-slim

WORKDIR /src

COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-cache

COPY src ./src
COPY .env .env

CMD ["streamlit", "run", ".\src\app.py"]