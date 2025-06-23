ARG PYTHON_VERSION=3.12-slim-bookworm
FROM python:${PYTHON_VERSION}

# For available labels, see OCI Annotations Spec docs:
# https://specs.opencontainers.org/image-spec/annotations/#pre-defined-annotation-keys
LABEL org.opencontainers.image.source="https://github.com/cloudinary/cloudinary-cli"
LABEL org.opencontainers.image.description="Cloudinary CLI - Command line interface for Cloudinary"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user (Debian/Ubuntu syntax)
RUN groupadd --gid 1000 cloudinary && \
    useradd --uid 1000 --gid cloudinary --shell /bin/bash --create-home cloudinary

# Set working directory
WORKDIR /app

# Install only cloudinary-cli from PyPI (lightweight approach)
RUN pip install --no-cache-dir cloudinary-cli

# Change ownership of working directory
RUN chown -R cloudinary:cloudinary /app

# Switch to non-root user
USER cloudinary

# Health check to verify CLI is working
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD cloudinary --version || exit 1

ENTRYPOINT ["cloudinary"]
