FROM python:3.10-slim

WORKDIR /app

COPY main.py .

RUN pip install fastapi uvicorn docker pydantic pandas scipy

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
