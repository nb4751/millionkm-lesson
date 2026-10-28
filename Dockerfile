FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home lesson \
    && mkdir -p /data /app/staticfiles \
    && chown -R lesson:lesson /data /app
COPY --chown=lesson:lesson . /app
RUN chmod +x /app/scripts/start_server.sh
USER lesson
EXPOSE 8000
CMD ["/app/scripts/start_server.sh"]
