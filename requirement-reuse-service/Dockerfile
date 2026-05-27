FROM python:3.12-slim

WORKDIR /service

COPY requirement-reuse-service/requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r /service/requirements.txt

COPY requirement-reuse-service/requirement_reuse_service /service/requirement_reuse_service

EXPOSE 8010

CMD ["uvicorn", "requirement_reuse_service.main:app", "--host", "0.0.0.0", "--port", "8010"]
