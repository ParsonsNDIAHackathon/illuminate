FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.9.24 \
    && uv sync --frozen --no-dev --no-install-project
COPY illuminate ./illuminate
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
ENV ILLUMINATE_DATA_DIR=/data
RUN addgroup --system illuminate && adduser --system --ingroup illuminate illuminate \
    && mkdir -p /data && chown illuminate:illuminate /data
USER illuminate
EXPOSE 8000
CMD ["uvicorn", "illuminate.main:app", "--host", "0.0.0.0", "--port", "8000"]
