ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION:-3.12-slim}

RUN pip3 install --no-cache cloudinary-cli

ENTRYPOINT [ "cloudinary" ]
