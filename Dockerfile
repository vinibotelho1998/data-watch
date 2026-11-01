FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
COPY src ./src
COPY data ./data
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && python -m data_watch train
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8005
CMD ["uvicorn", "data_watch.api:app", "--host", "0.0.0.0", "--port", "8005"]

