FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --no-compile . \
    && useradd --create-home --uid 10001 app

FROM base AS cli

USER app

ENTRYPOINT ["gh-screener"]
CMD ["--help"]

FROM base AS streamlit

RUN pip install --no-cache-dir --no-compile ".[web]"

COPY --chown=app:app interface ./interface

USER app

EXPOSE 8501

CMD ["streamlit", "run", "interface/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
