FROM python:3.11-slim

WORKDIR /app
ARG CACHE_BUST=1

# Set production environment
ENV ENV=production
ENV DEBUG=False

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install psycopg[binary] asyncpg alembic

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
