FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src /app/src

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

# Entry point
CMD ["python", "src/main.py"]
