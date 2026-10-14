FROM python:3.12-slim

WORKDIR /app
COPY server.py integrations.py ./
COPY static ./static

# Banco e chave-mestra fora do codigo, em volume persistente
ENV PORT=8000 PV_DB_PATH=/app/data/plataformavenda.db PV_UPLOAD_DIR=/app/data/uploads
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python3", "server.py"]
