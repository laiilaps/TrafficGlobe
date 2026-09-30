FROM python:3.12-alpine
# Für Produktion das Basisimage per Digest festnageln (python@sha256:...).
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY update.py ./
USER 1000:1000
CMD ["python", "-u", "/app/update.py"]
