FROM python:3.12-slim
WORKDIR /app
COPY receiver.py .
RUN useradd --create-home app && mkdir -p /app/data && chown app /app/data
USER app
ENV RESULTS_DIR=/app/data/results EVENTS_DB=/app/data/events.db PORT=8000
EXPOSE 8000
CMD ["python", "receiver.py"]
