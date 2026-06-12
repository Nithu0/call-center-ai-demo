# =====================================================================
#  Call-senter AI-demo (Loyalty) — produksjons-image
# =====================================================================
#  KJERNEPOENG: SAMME image kjører lokalt ELLER på Azure Container Apps.
#  Lokalt:  docker run -e DEPLOY_TARGET=local  -p 8000:8000 <image>
#  Azure:   DEPLOY_TARGET=azure + Azure-nøkler injiseres som secrets/env.
#  Ingen kodeendring — kun env-variabler bytter providere (se app/config.py).
# =====================================================================

FROM python:3.11-slim

# Uvicorn/Python-vennlige defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Installer avhengigheter først (bedre layer-caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopier applikasjonen (.dockerignore holder .venv/__pycache__/secrets ute)
COPY . .

# Kjør som ikke-root (god praksis; Container Apps krever det ikke, men trygt)
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Azure Container Apps injiserer $PORT (default 8000 lokalt). Bind 0.0.0.0.
EXPOSE 8000

# Enkel container-helsesjekk mot appens /healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz'; \
sys.exit(0) if urllib.request.urlopen(url, timeout=3).status==200 else sys.exit(1)"

# Ingen --reload i produksjon. Bruk sh -c slik at $PORT ekspanderes ved runtime.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
