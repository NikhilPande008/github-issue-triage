FROM python:3.12-slim-bookworm AS python

FROM node:22-bookworm-slim

COPY --from=python /usr/local /usr/local

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex

WORKDIR /workspace/repo
