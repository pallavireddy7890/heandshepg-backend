FROM python:3.11-slim

WORKDIR /app
ARG CACHE_BUST=1

# Set production environment
ENV APP_ENV=production
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
# Copy and set entrypoint
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
