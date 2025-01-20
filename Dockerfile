# syntax=docker/dockerfile:1

ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION:-3.12-slim}

# For available labels, see OCI Annotations Spec docs:
# https://specs.opencontainers.org/image-spec/annotations/#pre-defined-annotation-keys
LABEL org.opencontainers.image.source="https://github.com/cloudinary/cloudinary-cli"

RUN pip3 install --no-cache cloudinary-cli

ENTRYPOINT [ "cloudinary" ]
