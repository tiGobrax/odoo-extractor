# Build stage - instala dependências que podem precisar de compilação
FROM python:3.11-slim as builder

WORKDIR /app

# Instala dependências de build (se necessário para compilar pacotes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage - imagem final otimizada
FROM python:3.11-slim

WORKDIR /app

# Copia dependências Python do stage de build
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia código da aplicação
COPY src/ ./src/

# Cria usuário não-root para segurança
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Muda para usuário não-root (bibliotecas Python são legíveis por todos)
USER appuser

# Healthcheck (opcional - útil para Kubernetes/Orchestration)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Ponto de entrada
CMD ["python", "-m", "src.main"]