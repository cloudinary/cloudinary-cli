[![Build Status](https://app.travis-ci.com/cloudinary/cloudinary-cli.svg)](https://app.travis-ci.com/cloudinary/cloudinary-cli)
[![PyPI Downloads](https://img.shields.io/pypi/dm/cloudinary-cli.svg)](https://pypistats.org/packages/cloudinary-cli)
[![PyPI License](https://img.shields.io/pypi/l/cloudinary-cli.svg)](LICENSE)

# Cloudinary CLI

## Features
The Cloudinary CLI (Command Line Interface) enables you to interact with Cloudinary through the command line. For example, you can perform Admin and Upload API operations by typing commands into a terminal without having to spend time setting up a formal coding environment. Additional helper commands are provided to help you to try out transformations, optimizations, and other common actions with minimal effort. You can also combine CLI commands in a batch file to automate laborious tasks.

It is fully documented at [https://cloudinary.com/documentation/cloudinary_cli](https://cloudinary.com/documentation/cloudinary_cli).

## Requirements
Your own Cloudinary account.  If you don't already have one, sign up at [https://cloudinary.com/users/register/free](https://cloudinary.com/users/register/free).

Python 3.8 or later.  You can install Python from [https://www.python.org/](https://www.python.org/). Note that the Python Package Installer (pip) is installed with it.

## Setup and Installation

1. To install this package, run: `pip3 install cloudinary-cli`
2. Point your `cld` commands at a Cloudinary account using **either** of the following:

    **Option A — Log in with OAuth (recommended).** Run:

    ```
    cld login
    ```

    This opens your browser to authorize the CLI, then saves the login as a configuration (named after the cloud) and sets it as the default. No API secret is stored on disk — the saved login holds a short-lived token that the CLI refreshes automatically.

    **Option B — Set your CLOUDINARY\_URL environment variable.** For example:
    * On Mac or Linux:<br>`export CLOUDINARY_URL=cloudinary://123456789012345:abcdefghijklmnopqrstuvwxyzA@cloud_name`
    * On Windows (cmd.exe):<br>`set CLOUDINARY_URL=cloudinary://123456789012345:abcdefghijklmnopqrstuvwxyzA@cloud_name`
    * On Windows (PowerShell):<br>`$Env:CLOUDINARY_URL="cloudinary://123456789012345:abcdefghijklmnopqrstuvwxyzA@cloud_name"`

_**Note:** you can copy and paste your account environment variable from the Account Details section of the Dashboard page in the Cloudinary console._

3. Check your configuration by running `cld config`. A response of the following form is returned:

    ```
    cloud_name:     <CLOUD_NAME>
    api_key:        <API_KEY>
    api_secret:     ***************<LAST_4_DIGITS>
    private_cdn:    <True|False>
    ```

    If you get an error message when running `cld config`, you may need to add your Python installation to your $PATH. To do so, you can run `PATH="$PATH:/Library/Python/Versions/3.8/bin"` in your terminal, and add `export PATH="$PATH:/Library/Python/Versions/3.8/bin"` to your `/.bash_profile` or `~/.zshrc`.

## Quickstart

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#command_overview).

```
Usage: cld [cli options] [command] [command options] [method] [method parameters]
```

### Important commands

```
cld --help         # Lists available commands.
cld login          # Logs in to a Cloudinary account via OAuth in your browser.
cld logout         # Removes a saved OAuth login.
cld search --help  # Shows usage for the Search API.
cld admin          # Lists Admin API methods.
cld uploader       # Lists Upload API methods.
```

## Docker Usage

The Cloudinary CLI is also available as a Docker image, perfect for containerized environments, CI/CD pipelines, or when you prefer not to install Python locally.

### Quick Docker Examples

```sh
# Check configuration
docker run --rm -e CLOUDINARY_URL cloudinary/cli config

# Upload files from your local machine
docker run --rm -e CLOUDINARY_URL \
  -v /path/to/your/images:/app/images \
  cloudinary/cli uploader upload /app/images/sample.jpg

# Search for assets
docker run --rm -e CLOUDINARY_URL \
  cloudinary/cli search "resource_type:image" --max_results 5

# Interactive mode for multiple commands
docker run --rm -it -e CLOUDINARY_URL --entrypoint /bin/bash cloudinary/cli
```

**Docker Image**: `cloudinary/cli` • **Base**: Debian 12 • **Size**: ~175MB • **Multi-arch**: amd64, arm64

For comprehensive Docker usage, examples, and troubleshooting, see [DOCKER.md](DOCKER.md).

## Upload API

Enables you to run any methods that can be called through the upload API.

You can find documentation for each of the Upload API methods at [https://cloudinary.com/documentation/image_upload_api_reference](https://cloudinary.com/documentation/image_upload_api_reference).

The basic syntax using the Upload API is as follows:

```
cld [cli options] uploader [command options] [method] [method parameters]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#uploader).

Example: change the asset with `public_id:"flowers"` from `type:upload` to `type:private` and rename it using the rename method, which takes two parameters - `from_public_id` and `to_public_id`.

Use any of the following commands:

```
cld uploader rename flowers secret_flowers to_type=private
cld uploader rename flowers secret_flowers -o to_type private
cld rename flowers secret_flowers to_type=private

```

_**Note:** you can omit 'uploader' from the command when calling an Upload API method._

## Admin API

Enables you to run any methods that can be called through the admin API.

You can find documentation for each of the Admin API methods at [https://cloudinary.com/documentation/admin_api](https://cloudinary.com/documentation/admin_api).

The basic syntax using the Admin API is as follows:

```
cld [cli options] admin [command options] [method] [method parameters]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#admin).

Example: create a transformation and get information about that transformation:

```
cld admin create_transformation my_new_transformation w_500,h_500,c_crop,e_vectorize
cld admin transformation my_new_transformation
```

_**Note:** you can omit 'admin' from the command when calling an Admin API method._

## Search API

Runs the admin API search method, allowing you to use a Lucene query string as the expression.

You can find documentation for the Search API at [https://cloudinary.com/documentation/search_api](https://cloudinary.com/documentation/search_api).

The basic syntax using the Search API is as follows:

```
cld [cli options] search [command options] [expression]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#search).

## Other commands

### `url`
Generates a Cloudinary URL, which you can optionally open in your browser.

```
cld [cli options] url [command options] public_id [transformation]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#url).

Example: generate a URL that displays the image in your media library that has the public ID of 'sample', with a width of 500 pixels and transformed using the cartoonify effect, then open this URL in a browser.

```
cld url -rt image -t upload -o sample w_500,e_cartoonify
```
The URL that is returned is:

```
http://res.cloudinary.com/<YOUR CLOUD NAME>/image/upload/w_500,e_cartoonify/sample
```

### `make`

Returns template code for implementing the specified Cloudinary widget.

```
cld [cli options] make [command options] [widget]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#make).

Example: output the HTML required to embed the Upload Widget on your website.

```
cld make upload_widget
```

### `upload_dir`

Uploads a folder of assets, maintaining the folder structure.

```
cld [cli options] upload_dir [command options] [local_folder]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#upload_dir).

Example: upload the local folder, my_images, and all its contents and sub-folders to your Cloudinary folder my_images_on_cloudinary.

```
cld upload_dir -f my_images_on_cloudinary my_images
```

### `sync`

Synchronizes between a local folder and a Cloudinary folder, maintaining the folder structure.

```
cld [cli options] sync [command options] local_folder cloudinary_folder
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#sync).

Example: push up changes from the local folder, my_images, to your Cloudinary folder, my_images_on_cloudinary/my_images.

```
cld sync --push my_images my_images_on_cloudinary/my_images
```

### `migrate`

Migrates a list of external media files to Cloudinary. The URLs of the files to migrate are listed in a separate file and must all have the same prefix.

```
cld [cli options] migrate [command options] upload_mapping file
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#migrate).

## Additional configurations

A configuration is a reference to a specified Cloudinary account or cloud name via its environment variable.  You set the default configuration during setup and installation. Using different configurations allows you to access different Cloudinary cloud names, such as sub-accounts of your main Cloudinary account, or any additional Cloudinary accounts you may have.

The `config` command displays the current configuration and lets you manage additional configurations.

You can specify the environment variable of additional Cloudinary accounts either explicitly (`-c` option) or as a saved configuration (`-C` option).

For example, using the `-c` option:

```
cld -c cloudinary://123456789012345:abcdefghijklmnopqrstuvwxyzA@cloud_name admin usage
```

Whereas using the saved configuration "accountx":

```
cld -C accountx admin usage
```

_**Caution:** A saved API-key configuration stores your API secret in a local file. An OAuth login (see below) avoids this by storing a short-lived, auto-refreshed token instead._

You can create, delete and list saved configurations using the `config` command.

```
cld config [options]
```

For details, see the [Cloudinary CLI documentation](https://cloudinary.com/documentation/cloudinary_cli#config).

### Logging in with OAuth

Instead of saving an API key and secret, you can log in to a Cloudinary account through your browser. The CLI saves the resulting session as a named configuration and refreshes its token automatically.

```
cld login                  # Log in and save the configuration (named after the cloud).
cld login my-account       # Save the login under a specific name.
cld logout                 # Choose a saved OAuth login to remove.
cld logout my-account      # Remove a specific saved OAuth login.
```

Once saved, an OAuth login is selected with `-C <name>` just like any other saved configuration.

### Choosing a default configuration

The default configuration is used when no `-c`/`-C` option is given and no `CLOUDINARY_URL` environment variable is set. The first OAuth login becomes the default automatically; you can change it at any time.

```
cld config -d <name>           # Set an existing saved configuration as the default.
cld config --unset-default     # Clear the stored default.
cld config -ls                 # List saved configurations, marking the default and the active one.
```

When creating a configuration with `-n` or `--from_url`, add `--set-default` to make it the default in the same step. Resolution precedence is: `-c` (inline URL) > `-C` (saved name) > stored default > `CLOUDINARY_URL` environment variable.

### Refreshing OAuth tokens

OAuth tokens are refreshed automatically as needed, but you can refresh them manually.

```
cld config --refresh <name>    # Refresh a saved OAuth configuration's token.
cld config --refresh-all       # Refresh every saved OAuth configuration whose token is stale.
cld config --refresh <name> --force   # Refresh even if the token is still fresh.
```

If a token can no longer be refreshed (for example, the login was revoked), the CLI reports the configuration and the `cld login` command to use to log in again.
