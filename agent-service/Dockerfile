FROM python:3.12-slim
WORKDIR /app/agent-service
COPY agent-service/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY agent-service/app ./app
COPY contracts /app/contracts
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
