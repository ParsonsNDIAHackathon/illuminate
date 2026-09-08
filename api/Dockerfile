FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY illuminate ./illuminate
RUN pip install --no-cache-dir .
ENV ILLUMINATE_DATA_DIR=/data
RUN addgroup --system illuminate && adduser --system --ingroup illuminate illuminate \
    && mkdir -p /data && chown illuminate:illuminate /data
USER illuminate
EXPOSE 8000
CMD ["uvicorn", "illuminate.main:app", "--host", "0.0.0.0", "--port", "8000"]
