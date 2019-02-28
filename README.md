# Cloudinary CLI

## Features
This command line interface is fully and seamlessly integrated with Cloudinary's APIs. 

## Requirements
Python 3.x

## Setup

1. Set your CLOUDINARY_URL environment variable by adding `export CLOUDINARY_URL=<YOUR_CLOUDINARY_URL>` to your terminal configuration file (using `~/.bash_profile` as an example here):
    
    ```
    echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.bash_profile && source ~/.bash_profile
    ```

2. To install this package, run: `pip3 install cloudinary-cli`
3. Make sure your configuration is set up properly by running `cld whoami`. It should print:

    ```
    cloud_name:     <YOUR_CLOUD_NAME>
    api_key:        <API_KEY>
    ```

## Quickstart

### Important commands

```
cld --help # lists available commands
cld search --help 	# Search API usage
cld admin --ls 		# Admin API functions
cld uploader --ls 	# Upload API functions
cld upload --help	# Custom upload function
```

Using temporary Cloudinary configurations requires the `-c` option:

```
cld -c <CLOUDINARY_URL> <COMMAND> <OPTIONS> <PARAMS>
```

## Upload API

Bindings for the Upload API.

The basic syntax using the Upload API is as follows:

```
Usage: cld uploader [OPTIONS] [PARAMS]...

  Upload API bindings
  format: cld uploader <function> <parameters> <optional_parameters>
          eg. cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers
                OR
              cld uploader upload http://res.cloudinary.com/demo/image/upload/sample -o public_id flowers

Options:
  -o, --optional_param TEXT...  Pass optional parameters as raw strings
  -ls, --ls                     List all available functions in the Upload API
  --help                        Show this message and exit.
```

Example: I want to change the asset with `public_id:"flowers"` from `type:upload` to `type:private` using the rename method, which takes two parameters - `from_public_id` and `to_public_id`.

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
			  cld admin resources max_results=10 -o tags sample

Options:
  -o, --optional_param TEXT...  Pass optional parameters as raw strings
  -ls, --ls                     List all available functions in the Admin API
  --help                        Show this message and exit.
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
  Usage: cld search <Lucene query search string> <options>
  (eg. cld search cat AND tags:kitten -s public_id desc -f context -f tags -n 10)

Options:
  -f, --with_field TEXT      Field to include in the result
  -s, --sort_by TEXT...      Sort search results by (field, <asc|desc>)
  -a, --aggregate TEXT       Aggregation to apply to the query
  -n, --max_results INTEGER  Maximum results to return. default: 10 max: 500
  -c, --next_cursor TEXT     Continue a search using an existing cursor
  --help                     Show this message and exit.
```

## Other basic commands
- `url` - generates a Cloudinary URL for an asset
- `config` - current Cloudinary CLI configuration

## Custom commands
- `upload_dir` - Uploads a directory to Cloudinary and persists the folder structure.
- `ls` - Lists all resources based on resource search parameters in your cloud and returns specific fields (all if none is specified). Note - this uses multiple Admin API calls.
- `make` - Scaffolds a template. Currently limited to HTML templates for Upload Widget, Product Gallery, Video Player, and Media Library, and a few Python scripts.

## Sample resources

Opens a demo account URL for a sample resource

Usage:

```
cld <sample_resource> <transformation>
```

- `sample` - http://res.cloudinary.com/demo/image/upload/sample
- `couple` - http://res.cloudinary.com/demo/image/upload/couple
- `dog` - http://res.cloudinary.com/demo/video/upload/dog