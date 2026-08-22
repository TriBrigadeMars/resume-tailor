# ResumeTailor — self-hosted AI resume & cover letter generator
FROM python:3.11-slim

# System deps: PyMuPDF libs + curl (to fetch NodeSource) + ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js + npm so npx-based stdio MCP servers work in containers
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py llm.py docgen.py search.py mcp_integration.py rss.py ./
COPY templates ./templates
COPY static ./static

# Run as a non-root user for safety
RUN useradd -m appuser
USER appuser

# Container defaults: bind all interfaces, fixed port, no browser auto-open
ENV HOST=0.0.0.0 \
    PORT=8000 \
    AUTO_OPEN_BROWSER=0

EXPOSE 8000

CMD ["python", "app.py"]
