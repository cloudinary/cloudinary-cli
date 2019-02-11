# Cloudinary CLI

## Features

This command line interface is fully and (almost: see Caveats) seamlessly integrated with Cloudinary's Upload, Search, and Admin APIs via the pycloudinary SDK.

Additional features include:

- Code generation
- Directory uploading
- Listing files

## Requirements

Python 3.x

## Getting started

Set your CLOUDINARY_URL environment variable by adding `export CLOUDINARY_URL=<YOUR_CLOUDINARY_URL>` to your terminal config file.

```
echo "export CLOUDINARY_URL=YOUR_CLOUDINARY_URL" >> ~/.profile
```

To install this package, run:

```
pip3 install cloudinary-cli
```

## Quickstart

#### 5 commands to help you get started:

- `cld --help` lists the available functions
- `cld upload --help` lists options for uploading
- `cld admin -ls` lists functions available in the Admin API
- `cld uploader -ls` lists functions available in the Upload API
- `cld search --help` Search API parameters

## Docs

Most of the functionality (functions to call, parameters, options) is dependent on [Cloudinary's official documentation](https://cloudinary.com/documentation/image_upload_api_reference).

### Upload

`cld upload <resource_type> <options>`

Example:
```
cld upload https://res.cloudinary.com/demo/image/upload/sample -t w_500,e_vectorize,ar_1 -pid nice_flowers
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_upload.gif)

```
Usage: cld upload [OPTIONS] IMGSTRING

Options:
  -pid, --public_id
  -type, --_type
  -up, --upload_preset
  -t, --transformation       A raw transformation
                             (eg. f_auto,q_auto,w_500,e_vectorize)
  -e, --eager                An eager transformation or an array of eager
                             transformations
  -o, --options              Options to use (eg. -o
                             option1=value1&option2=value2)
  -open, --open              Opens the image in a new window
  --help                     Show this message and exit.
```

### Upload API bindings

`cld uploader <method> <args> <kwargs>`

Example:
```
cld uploader upload http://res.cloudinary.com/demo/image/upload/sample public_id=flowers
cld uploader rename flowers secret_flowers to_type=private
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_uploader.gif)

### Search API bindings

`cld search <lucene query string>`

Example:
```
cld search cat AND tags:kitten -f context -f tags -n 10
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_search.gif)

### Admin API bindings

`cld admin <method> <args> <kwargs>`

Example:
```
cld admin resources max_results=10 prefix=sample
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_admin.gif)

### Additional features

#### Listing all files

`cld ls <field(s) to return and/or resource queries>`

Basic usage:
`cld ls`

The following statements are equivalent:

```
cld ls public_id url type=private resource_type=image
cld ls type=private resource_type=image public_id url
cld ls type=private public_id url resource_type=image
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_ls.gif)


#### Uploading a local directory

Upload a local directory and preserve the folder structure.

`cld upload_dir <directory_name>`

Example:

```
cld upload_dir ~/Desktop/my_directory -v -f my_local_folder
```

![](http://res.cloudinary.com/brianl/image/upload/docs/docs_upload_dir.gif)


#### Code Sample Generation

`cld make <language> <name of template>`

eg. 
The following statements are equivalent:
```
cld make html upload widget
cld make upload_widget html
cld make upload widget
```

For language-specific templates, include the language in the command

eg.
`cld make python upload` or `cld make upload python`

### Caveats

- Passing a parameter or option as a list or object must be encapsulated in single quotes, and strings within in double quotes.
    - '["this","will","be","read","as","a","list"]'
    - '{"an":"object","or":"dict"}'


- Passing a string that can be evaluated as an object, list, or boolean will be evaluated as such, so please refrain from such naming conventions in your public_id, upload_preset, or named transformation:
    - 'True'
    - 'true'
    - '["public","ids","looking","like","lists","wont","work"]'
    - '{"not":"okay"}'