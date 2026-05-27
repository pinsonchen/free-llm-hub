FROM python:3.12-slim AS runtime

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system -e "."

COPY . .

EXPOSE 8787

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
