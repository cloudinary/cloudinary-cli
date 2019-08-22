# Cloudinary CLI

## Features
This command line interface is fully and seamlessly integrated with Cloudinary's APIs.

## Requirements
Python 3.6

## Setup

1. Set your CLOUDINARY_URL environment variable by adding `export CLOUDINARY_URL=<YOUR_CLOUDINARY_URL>` to your terminal configuration file (using `~/.bash_profile` as an example here):
    
    ```
    echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.bash_profile && source ~/.bash_profile
    ```

2. To install this package, run: `pip3 install cloudinary-cli`
3. Make sure your configuration is set up properly by running `cld config`. It should print:

    ```
    cloud_name:     <CLOUD_NAME>
    api_key:        <API_KEY>
    api_secret:     ***************<LAST_4>
    private_cdn:    <True|False>
    ```

## Quickstart

### Important commands

```
cld --help # lists available commands
cld search --help 	# Search API usage
cld admin     # Admin API functions
cld uploader    # Upload API functions
```

Using temporary Cloudinary configurations requires the `-c` option or `--config`:

```
cld -c <CLOUDINARY_URL> <COMMAND> <OPTIONS> <PARAMS>
```

Additional configurations can be used by using the `-C` option.

```
cld -C my_subaccount admin resources
```

## Additional configurations

```
Usage: cld config [OPTIONS]

  Display current configuration

Options:
  -n, --new TEXT...  Set an additional configuration
                     eg. cld config -n <NAME> <CLOUDINARY_URL>
  -ls, --ls          List all configurations
  -rm, --rm TEXT     Delete an additional configuration
  -url, --from_url TEXT  Create a configuration from a Cloudinary URL
  --help             Show this message and exit.
```

## Upload API

Bindings for the Upload API.

The basic syntax using the Upload API is as follows:

```
Usage: cld uploader [OPTIONS] [PARAMS]...

  Upload API bindings
  format: cld uploader <function> <parameters> <optional_parameters>
          eg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
  
          eg. cld uploader rename flowers secret_flowers to_type=private
                OR
              cld uploader rename flowers secret_flowers -o to_type private

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -ls, --ls                       List all available functions in the Upload API
  --save TEXT                     Save output to a file
  -d, --doc                       Opens Upload API documentation page
  --help                          Show this message and exit.
```

Example: I want to change the asset with `public_id:"flowers"` from `type:upload` to `type:private` and rename it using the rename method, which takes two parameters - `from_public_id` and `to_public_id`.

The following two commands will do the same thing:

```
cld uploader rename flowers secret_flowers to_type=private
cld uploader rename flowers secret_flowers -o to_type private
```

## Admin API

Bindings for the Admin API follows the same format as the Upload API:

```
Usage: cld admin [OPTIONS] [PARAMS]...

  Admin API bindings
  format: cld admin <function> <parameters> <optional_parameters>
          eg. cld admin resources max_results=10 tags=sample
                OR
              cld admin resources -o max_results 10 -o tags sample
                OR
              cld admin resources max_results=10 -o tags=sample

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -ls, --ls                       List all available functions in the Admin API
  --save TEXT                     Save output to a file
  -d, --doc                       Opens Admin API documentation page
  --help                          Show this message and exit.
```

Example: I want to create a transformation and get information about that transformation:

```
cld admin create_transformation my_new_transformation w_500,h_500,c_crop,e_vectorize
cld admin transformation my_new_transformation
```

## Search API

Search API bindings allow you to enter in a Lucene query string as the expression.

```
Usage: cld search [OPTIONS] [QUERY]...

  Search API bindings
  format: cld search <Lucene query syntax string> <options>
  eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10

Options:
  -f, --with_field TEXT      Field to include in result
  -s, --sort_by TEXT...      Sort search results by (field, <asc|desc>)
  -a, --aggregate TEXT       Aggregation to apply to the query
  -n, --max_results INTEGER  Maximum results to return. default: 10 max: 500
  -c, --next_cursor TEXT     Continue a search using an existing cursor
  -A, --auto_paginate        Return all results. Will call Admin API multiple times.
  -F, --force                Skip confirmation when running --auto-paginate
  -ff, --filter_fields TEXT  Filter fields to return
  --json TEXT                Save output as a JSON. Usage: --json <filename>
  --csv TEXT                 Save output as a CSV. Usage: --csv <filename>
  -d, --doc                  Opens Search API documentation page
  --help                     Show this message and exit.
```

## Other basic commands

### `url`

```
Usage: cld url [OPTIONS] PUBLIC_ID [TRANSFORMATION]

  Generate a cloudinary url

Options:
  -rt, --resource_type [image|video|raw]
                                  Resource Type
  -t, --type [upload|private|authenticated|fetch|list]
                                  Type of the resource
  -o, --open                      Open URL in your browser
  -s, --sign                      Generates a signed URL
  --help                          Show this message and exit.
```

### `config`

```

Usage: cld config [OPTIONS]

  Display current configuration, and manage additional configurations

Options:
  -n, --new TEXT...  Set an additional configuration
                     eg. cld config -n <NAME> <CLOUDINARY_URL>
  -ls, --ls          List all configurations
  -rm, --rm TEXT     Delete a saved configuration
  --help             Show this message and exit.
```

## Custom commands

### `upload_dir`

Uploads a directory to Cloudinary and persists the folder structure.

```
Usage: cld upload_dir [OPTIONS] [DIRECTORY]

  Upload a directory of assets and persist the directory structure

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -t, --transformation TEXT       Transformation to apply on all uploads
  -f, --folder TEXT               Specify the folder you would like to upload resources to in Cloudinary
  -p, --preset TEXT               Upload preset to use
  -v, --verbose                   Logs information after each upload
  -vv, --very_verbose             Logs full details of each upload
  --help                          Show this message and exit.
  ```

### `make`

Scaffolds a template. Currently limited to HTML templates for Upload Widget, Product Gallery, Video Player, and Media Library, and a few Python scripts.

```
Usage: cld make [OPTIONS] [TEMPLATE]...

  Scaffold Cloudinary templates.
  eg. cld make product gallery

Options:
  --help  Show this message and exit.
```

### `sync`

Synchronize between a local folder and a Cloudinary folder.

```
Usage: cld sync [OPTIONS] LOCAL_FOLDER CLOUDINARY_FOLDER

  Synchronize between a local directory between a Cloudinary folder while preserving directory structure

Options:
  --push         Push will sync the local directory to the cloudinary directory
  --pull         Pull will sync the cloudinary directory to the local directory
  -v, --verbose  Logs information after each upload
  --help         Show this message and exit.
```

### `migrate`

Force migrate assets using an auto-upload preset.

```
Usage: cld migrate [OPTIONS] UPLOAD_MAPPING FILE

  Migrate files using an existing auto-upload mapping and a file of URLs

Options:
  -d, --delimiter TEXT  Separator for the URLs. Default: New line
  -v, --verbose
  --help                Show this message and exit.
```

## Sample resources

Opens a demo account URL for a sample resource

Usage:

```
cld <sample_resource> <transformation>
```

- `sample` - http://res.cloudinary.com/demo/image/upload/sample
- `couple` - http://res.cloudinary.com/demo/image/upload/couple
- `dog` - http://res.cloudinary.com/demo/video/upload/dog

# TODOs
- Globbing support
- Local GUI support
- More code samples