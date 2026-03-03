FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster startups
ENV UV_COMPILE_BYTECODE=1
# Copy only the configuration files first to cache the installation layer
COPY pyproject.toml uv.lock ./

# Install dependencies without installing the project itself yet
RUN uv sync --frozen --no-install-project

# Copy the rest of your code
COPY . .

# Run your application
CMD ["uv", "run", "main.py"]