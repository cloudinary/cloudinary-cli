# Running Cloudinary CLI with Docker

This document provides instructions on how to build and run the Cloudinary CLI using Docker.

## Building the Image

You can build the Docker image in two ways: from a local clone of the repository or directly from GitHub.

### Building from a Local Clone

First, build the Docker image from the root of the project:

```sh
docker build -t cloudinary-cli .
```

### Building with Specific Python Version

You can specify the Python version using the `PYTHON_VERSION` build argument:

```sh
docker build --build-arg PYTHON_VERSION=3.11-slim-bookworm -t cloudinary-cli .
```

**Available Python versions:**
- `3.12-slim-bookworm` (default, recommended)
- `3.11-slim-bookworm`
- `3.10-slim-bookworm`

### Building from GitHub

You can also build the image directly from the GitHub repository without cloning it first:

```sh
docker build -t cloudinary-cli https://github.com/cloudinary/cloudinary-cli.git

# With custom Python version
docker build --build-arg PYTHON_VERSION=3.11-slim-bookworm \
  -t cloudinary-cli https://github.com/cloudinary/cloudinary-cli.git
```

## Build Architecture

The main `Dockerfile` uses a **single-stage build** approach:

- **Lightweight**: Installs `cloudinary-cli` directly from PyPI (no build dependencies)
- **Production-ready**: Uses the official published package
- **Efficient**: Minimal layers and fast build times
- **Secure**: Runs as non-root user with health checks

The `Dockerfile.dev` is designed for development and testing:

- **Source-based**: Builds from local source code in development mode
- **Development-friendly**: Allows testing changes without publishing to PyPI
- **Editable install**: Uses `pip install -e .` for live code changes

## Running the Container

The Cloudinary CLI requires Cloudinary credentials to run. You can provide these credentials using environment variables.

**Note:** Replace `<your_cloud_name>`, `<your_api_key>`, and `<your_api_secret>` with your actual Cloudinary credentials.

### Option 1: Using Individual Environment Variables

This is the recommended method for production use.

```sh
docker run --rm \
  -e CLOUDINARY_CLOUD_NAME="<your_cloud_name>" \
  -e CLOUDINARY_API_KEY="<your_api_key>" \
  -e CLOUDINARY_API_SECRET="<your_api_secret>" \
  cloudinary-cli config
```

**Note:** If you have these variables already set in your shell environment, you can pass them directly to the container without specifying the values:

```sh
docker run --rm \
  -e CLOUDINARY_CLOUD_NAME \
  -e CLOUDINARY_API_KEY \
  -e CLOUDINARY_API_SECRET \
  cloudinary-cli config
```

### Option 2: Using `CLOUDINARY_URL` Environment Variable

This method combines all credentials into a single URL (recommended for development).

```sh
docker run --rm \
  -e CLOUDINARY_URL="cloudinary://<your_api_key>:<your_api_secret>@<your_cloud_name>" \
  cloudinary-cli config
```

**Note:** If you have the `CLOUDINARY_URL` variable already set in your shell environment, you can pass it directly:

```sh
docker run --rm -e CLOUDINARY_URL cloudinary-cli config
```

## Common CLI Commands

### Check Configuration and Version

```sh
# Check configuration
docker run --rm -e CLOUDINARY_URL cloudinary-cli config

# Check version information
docker run --rm -e CLOUDINARY_URL cloudinary-cli --version
```

### Upload an Image

To upload files from your local machine, you need to mount a volume:

```sh
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/your/images:/app/images \
  cloudinary-cli uploader upload /app/images/sample.jpg folder=my_folder
```

### Search for Assets

```sh
# Search for images (limit results for better readability)
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli search "resource_type:image" --max_results 5

# Search with specific criteria
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli search "resource_type:image AND format:jpg" --max_results 3
```

### Generate a URL

```sh
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli url sample w_500,h_300
```

### Admin API Operations

```sh
# Get usage statistics
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli admin usage

# List all transformations
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli admin transformations

# List available admin methods
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli admin -ls
```

## Interactive Mode

You can run the container in interactive mode to execute multiple commands. Since the container uses `cld` as the entrypoint, you need to override it to access bash:

```sh
docker run --rm -it -e CLOUDINARY_URL --entrypoint /bin/bash cloudinary-cli
```

Then within the container, you can run CLI commands directly:

```sh
cld config
cld search "resource_type:image" --max_results 5
cld url sample w_500,h_300,c_fill
cld uploader upload /path/to/file.jpg folder=my_folder
```

### Running Multiple Commands in One Line

You can also run multiple commands without entering interactive mode:

```sh
docker run --rm -e CLOUDINARY_URL --entrypoint /bin/bash cloudinary-cli \
  -c "cld --version && cld config && cld search 'resource_type:image' --max_results 3"
```

## Working with Local Files

### Upload Directory

To upload a local directory, mount it as a volume:

```sh
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/local/folder:/app/upload \
  cloudinary-cli upload_dir /app/upload -f remote_folder_name
```

### Sync Directory

To sync a local directory with Cloudinary:

```sh
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/local/folder:/app/sync \
  cloudinary-cli sync --push /app/sync remote_folder_name
```

## Development Usage

### Building from Local Source

If you're developing the CLI, you can build from your local source code using the provided development Dockerfile:

```sh
docker build -f Dockerfile.dev -t cloudinary-cli-dev .
docker run --rm -e CLOUDINARY_URL cloudinary-cli-dev config
```

The development Dockerfile (`Dockerfile.dev`) differs from the main `Dockerfile` in several ways:

| Feature | `Dockerfile` (Production) | `Dockerfile.dev` (Development) |
|---------|---------------------------|--------------------------------|
| **Source** | PyPI package | Local source code |
| **Install method** | `pip install cloudinary-cli` | `pip install -e .` (editable) |
| **Use case** | Production deployments | Local development/testing |
| **Build time** | Fast (no compilation) | Slower (installs dependencies) |
| **Code changes** | Requires rebuild | Live reload with volume mount |

### Development with Volume Mounting

For active development, you can mount your local source code:

```sh
# Build the dev image once
docker build -f Dockerfile.dev -t cloudinary-cli-dev .

# Run with source code mounted for live changes
docker run --rm -e CLOUDINARY_URL \
  -v $(pwd):/app \
  --entrypoint /bin/bash \
  cloudinary-cli-dev -c "pip install -e . && cld config"
```

### Exploring Available Commands

List all available methods for different APIs:

```sh
# List all uploader methods
docker run --rm -e CLOUDINARY_URL cloudinary-cli uploader -ls

# List all admin methods
docker run --rm -e CLOUDINARY_URL cloudinary-cli admin -ls

# Get help for specific commands
docker run --rm -e CLOUDINARY_URL cloudinary-cli uploader --help
docker run --rm -e CLOUDINARY_URL cloudinary-cli search --help
```

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `CLOUDINARY_URL` | Complete Cloudinary URL | `cloudinary://api_key:api_secret@cloud_name` |
| `CLOUDINARY_CLOUD_NAME` | Your Cloudinary cloud name | `my-cloud` |
| `CLOUDINARY_API_KEY` | Your Cloudinary API key | `123456789012345` |
| `CLOUDINARY_API_SECRET` | Your Cloudinary API secret | `abcd1234...` |

## Practical Examples

### Real-world Upload Example

```sh
# Upload a single file to a specific folder
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/your/images:/app/images \
  cloudinary-cli uploader upload /app/images/photo.jpg folder=my_photos public_id=my_custom_name

# Upload with transformations applied immediately
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/your/images:/app/images \
  cloudinary-cli uploader upload /app/images/photo.jpg \
  transformation=w_800,h_600,c_fill folder=thumbnails
```

### Batch Operations

```sh
# Get account usage and limits
docker run --rm -e CLOUDINARY_URL cloudinary-cli admin usage

# Search and then generate URLs for found assets
docker run --rm -e CLOUDINARY_URL --entrypoint /bin/bash cloudinary-cli -c "
  echo 'Recent images:' &&
  cld search 'resource_type:image' --max_results 3 --fields public_id,format &&
  echo 'Sample transformation URL:' &&
  cld url sample w_500,h_300,c_fill
"
```

## Troubleshooting

### Common Issues and Solutions

#### 1. "No such command 'upload'" Error
**Problem**: Using `upload` instead of `uploader upload`
```sh
# ❌ Wrong
docker run --rm -e CLOUDINARY_URL cloudinary-cli upload file.jpg

# ✅ Correct
docker run --rm -e CLOUDINARY_URL cloudinary-cli uploader upload file.jpg
```

#### 2. Interactive Mode Not Working
**Problem**: Trying to access bash directly
```sh
# ❌ Wrong
docker run --rm -it -e CLOUDINARY_URL cloudinary-cli bash

# ✅ Correct
docker run --rm -it -e CLOUDINARY_URL --entrypoint /bin/bash cloudinary-cli
```

#### 3. File Upload Issues
**Problem**: File not found or permission issues
```sh
# Make sure to mount the directory containing your files
docker run --rm -e CLOUDINARY_URL \
  -v $(pwd)/images:/app/images \
  cloudinary-cli uploader upload /app/images/yourfile.jpg
```

### Check if CLI is Working

```sh
docker run --rm cloudinary-cli --version
```

### Debug Configuration Issues

```sh
docker run --rm -e CLOUDINARY_URL cloudinary-cli config
```

### View Help

```sh
docker run --rm cloudinary-cli --help
```

### Test Connection

```sh
docker run --rm -e CLOUDINARY_URL cloudinary-cli admin ping
```

If you encounter authentication errors, verify your credentials are correct and properly formatted.

## Security Considerations

- Never hardcode credentials in Dockerfiles or images
- Use environment variables or Docker secrets for credentials
- Consider using `--rm` flag to automatically remove containers after execution
- For production deployments, consider using Docker secrets or external secret management

## Examples

### Complete Workflow Example

```sh
# Build the image
docker build -t cloudinary-cli .

# Check configuration
docker run --rm -e CLOUDINARY_URL cloudinary-cli config

# Upload an image
docker run --rm -e CLOUDINARY_URL \
  -v ./images:/app/images \
  cloudinary-cli upload /app/images/photo.jpg public_id=my-photo

# Generate a transformation URL
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli url my-photo w_500,h_300,c_fill

# Search for the uploaded image
docker run --rm -e CLOUDINARY_URL \
  cloudinary-cli search "public_id:my-photo"
```
