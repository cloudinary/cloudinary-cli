# Cloudinary CLI

## Features
This command line interface is fully and seamlessly integrated with Cloudinary's APIs.

## Requirements
Your own Cloudinary account.  If you don't already have one, sign up at [https://cloudinary.com/users/register/free](https://cloudinary.com/users/register/free).

Python 3.6 or later.  You can install Python from [https://www.python.org/](https://www.python.org/). Note that the Python Package Installer (pip) is installed with it.

## Setup and Installation

1. Set your CLOUDINARY_URL environment variable by adding `export CLOUDINARY_URL=<YOUR_CLOUDINARY_URL>` to your terminal configuration file (using `~/.bash_profile` as an example here):
    
    ```
    echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.bash_profile && source ~/.bash_profile
    ```

_**Note:** you can copy and paste your Cloudinary URL from your console._

2. To install this package, run: `pip3 install cloudinary-cli`
3. Make sure your configuration is set up properly by running `cld config`. It should print:

    ```
    cloud_name:     <CLOUD_NAME>
    api_key:        <API_KEY>
    api_secret:     ***************<LAST_4>
    private_cdn:    <True|False>
    ```

## Quickstart

```
Usage: cld [OPTIONS] COMMAND [ARGS]...
```

### Important commands

```
cld --help         # Lists available commands
cld search --help  # Shows usage for the Search API
cld admin          # Lists Admin API methods
cld uploader       # Lists Upload API methods
```

## Upload API

Bindings for the Upload API.

You can find documentation for each of the Upload API methods at [https://cloudinary.com/documentation/image_upload_api_reference](https://cloudinary.com/documentation/image_upload_api_reference) 

The basic syntax using the Upload API is as follows:

```
Usage: cld uploader [OPTIONS] [PARAMS]...

  Upload API bindings
  format: cld uploader <method> <parameters> <optional_parameters>
          e.g. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers invalidate=True
  
          e.g. cld uploader rename flowers secret_flowers to_type=private
                OR
              cld uploader rename flowers secret_flowers -o to_type private

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -ls, --ls                       List all available methods in the Upload API
  --save TEXT                     Save output to a file
  -d, --doc                       Opens Upload API documentation page
  --help                          Show this message and exit.
```

Example: change the asset with `public_id:"flowers"` from `type:upload` to `type:private` and rename it using the rename method, which takes two parameters - `from_public_id` and `to_public_id`.

The following commands will do the same thing:

```
cld uploader rename flowers secret_flowers to_type=private
cld uploader rename flowers secret_flowers -o to_type private
cld rename flowers secret_flowers to_type=private

```

_**Note:** you can omit 'uploader' from the command when calling an Upload API method._

## Admin API

Bindings for the Admin API.

You can find documentation for each of the Admin API methods at [https://cloudinary.com/documentation/admin_api](https://cloudinary.com/documentation/admin_api)

```
Usage: cld admin [OPTIONS] [PARAMS]...

  Admin API bindings
  format: cld admin <method> <parameters> <optional_parameters>
          e.g. cld admin resources max_results=10 tags=sample
                OR
              cld admin resources -o max_results 10 -o tags sample
                OR
              cld admin resources max_results=10 -o tags sample

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -ls, --ls                       List all available methods in the Admin API
  --save TEXT                     Save output to a file
  -d, --doc                       Opens Admin API documentation page
  --help                          Show this message and exit.
```

Example: create a transformation and get information about that transformation:

```
cld admin create_transformation my_new_transformation w_500,h_500,c_crop,e_vectorize
cld admin transformation my_new_transformation
```

_**Note:** you can omit 'admin' from the command when calling an Admin API method._

## Search API

Search API bindings allow you to enter in a Lucene query string as the expression.

You can find documentation for the Search API at [https://cloudinary.com/documentation/search_api](https://cloudinary.com/documentation/search_api)

```
Usage: cld search [OPTIONS] [QUERY]...

  Search API bindings
  format: cld search <Lucene query syntax string> <options>
  e.g. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10

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

## Other commands

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

Example: generate a URL that displays the image in your media library that has the public ID of 'sample', with a width of 500 pixels and transformed using the cartoonify effect, then open this URL in a browser. 

```
cld url -rt image -t upload -o sample w_500,e_cartoonify
```
The URL that is returned is:

```
http://res.cloudinary.com/<YOUR CLOUD NAME>/image/upload/w_500,e_cartoonify/sample
```

### `make`

Scaffolds a template. Currently limited to HTML templates for Upload Widget, Product Gallery, Video Player, and Media Library, and a few Python scripts.

```
Usage: cld make [OPTIONS] [TEMPLATE]...

  Scaffold Cloudinary templates.
  e.g. cld make product gallery

Options:
  --help  Show this message and exit.

Template:
   media_library_widget
   product_gallery
   upload_widget
   video_player  
```

Example: output the HTML required to embed the Upload Widget on your website.

```
cld make upload_widget
```

### `upload_dir`

Uploads a directory to Cloudinary maintaining the folder structure.

```
Usage: cld upload_dir [OPTIONS] [DIRECTORY]

  Upload a directory of assets and persist the directory structure

Options:
  -o, --optional_parameter TEXT...
                                  Pass optional parameters as raw strings
  -O, --optional_parameter_parsed TEXT...
                                  Pass optional parameters as interpreted strings
  -t, --transformation TEXT       Transformation to apply on all uploads
  -f, --folder TEXT               Specify the folder you would like to upload resources to in Cloudinary.  If it does not exist, create it.
  -p, --preset TEXT               Upload preset to use
  -v, --verbose                   Logs information after each upload
  -vv, --very_verbose             Logs full details of each upload
  --help                          Show this message and exit.
  ```
  
Example: upload the local folder, my_images, and all its contents and sub-folders to your Cloudinary folder my_images_on_cloudinary.  

```
cld upload_dir -f my_images_on_cloudinary my_images
```

### `sync`

Synchronize between a local folder and a Cloudinary folder.

```
Usage: cld sync [OPTIONS] LOCAL_FOLDER CLOUDINARY_FOLDER

  Synchronize between a local directory and a Cloudinary folder while preserving directory structure

Options:
  --push         Push will sync the local directory to the Cloudinary directory
  --pull         Pull will sync the Cloudinary directory to the local directory
  -v, --verbose  Logs information after each upload
  --help         Show this message and exit.
```

Example: push up changes from the local folder, my_images, to your Cloudinary folder, my_images_on_cloudinary/my_images.

```
cld sync --push my_images my_images_on_cloudinary/my_images
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

## Additional configurations

If you have access to more than one Cloudinary account, you can specify the Cloudinary URL of other accounts inline with your command either as a temporary configuration or a saved configuration.  

Using temporary Cloudinary configurations requires the `-c` option or `--config`:

```
cld -c <CLOUDINARY_URL> COMMAND [ARGS]...
```

Saved configurations can be used by using the `-C` option.

```
cld -C <SAVED_CONFIGURATION> COMMAND [ARGS]...
```

Example: run the resources method from the Admin API using the configuration saved to my_subaccount.

```
cld -C my_subaccount admin resources
```

You can create a saved configuration using `cld config`.

```
Usage: cld config [OPTIONS]

  Display current configuration

Options:
  -n, --new TEXT...      Save an additional configuration
                         e.g. cld config -n <NAME>   <CLOUDINARY_URL>
  -ls, --ls              List all configurations
  -rm, --rm TEXT         Delete an additional configuration
  -url, --from_url TEXT  Create a configuration from a Cloudinary URL
  --help             Show this message and exit.
```


## Sample resources

Creates a URL based on a sample resource from the demo account.

Usage:

```
cld <sample_resource> <transformation>
```

- `sample` - http://res.cloudinary.com/demo/image/upload/sample
- `couple` - http://res.cloudinary.com/demo/image/upload/couple
- `dog` - http://res.cloudinary.com/demo/video/upload/dog

Example: create the URL for the dog video with optimized quality.

```
cld dog q_auto
```

# TODOs
- Globbing support
- Local GUI support
- More code samples