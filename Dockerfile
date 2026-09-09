FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV GOOGLE_GENAI_USE_VERTEXAI=FALSE HOUSELIGHTS_DB=/tmp/houselights PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["adk", "web", "agents", "--host", "0.0.0.0", "--port", "7860"]
