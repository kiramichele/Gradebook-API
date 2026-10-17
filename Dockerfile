# The API image. Railway builds this (see railway.json); it runs anywhere.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml README.md ./
RUN mkdir app && touch app/__init__.py \
    && pip install . \
    && pip uninstall -y gradebook-api \
    && rm -rf app

COPY app ./app
COPY scripts ./scripts
COPY supabase ./supabase
RUN pip install --no-deps .

RUN useradd --create-home --uid 10001 api
USER api

EXPOSE 8000
# Railway sets PORT. Proxy headers make request.url use the public https scheme.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]
