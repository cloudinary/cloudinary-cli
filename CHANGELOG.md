1.7.1 / 2023-05-17
==================

  * Fix package MANIFEST

1.7.0 / 2023-05-17
==================

New functionality and features
------------------------------

  * Add support for Search URL

Other Changes
-------------

  * Bump `pycloudinary` to `1.33.0`
  * Allow passing positional parameters as optional

1.6.2 / 2023-04-05
==================

  * Fix optional parameters handling in `upload_dir`

1.6.1 / 2023-02-23
==================

  * Fix `migrate` command on Windows

1.6.0 / 2023-02-07
==================

New functionality and features
------------------------------

  * Add support for `--exclude-dir-name` option in `upload_dir`

1.5.1 / 2022-11-03
==================

  * Fix `sync` for files with `authenticated` access mode
  * Fix no configuration error message

1.5.0 / 2022-01-20
==================

New functionality and features
------------------------------

  * Add support for glob patterns in `upload_dir`
  * Bump `pycloudinary` to `1.28.1`
  * Improve API documentation
  
Other Changes
-------------

  * Improve error handling of the API commands
  * Improve error handling of CLI commands
  * Fix deprecation warning
  * Improve error handling of missing configuration
  * Refactor `sync` command
  * Sort commands in help strings
  * Normalize CLI options
  * Add unit tests

1.4.6 / 2021-11-18
==================

  * Fix `sync` on Windows
  * Fix integer parameters handling
  * Remove internal methods from help strings


1.4.5 / 2021-07-27
==================

  * Improve `sync` error handling
  * Fix syncing of raw files with uppercase extension

1.4.4 / 2021-07-04
==================

  * Fix `sync` file extension normalization

1.4.3 / 2021-06-28
==================

  * Fix `sync` of private assets

1.4.2 / 2021-06-22
==================

  * Fix `migrate` command

1.4.1 / 2021-05-03
==================

  * Fix issue with optional arguments

1.4.0 / 2021-03-26
==================

New functionality and features
------------------------------

  * Add support for auto-paginated Admin API calls
  * Add support for viewing details of saved configurations
  * Bump `pycloudinary` to `1.25.0`

Other Changes
-------------

  * Add release tools


1.3.1 / 2020-12-18
==================

  * Fix `upload_dir` error

1.3.0 / 2020-11-09
==================

New functionality and features
------------------------------

  * Add `include-hidden` option to `sync`
  * Add `deletion-batch-size` option to `sync`

Other Changes
-------------

  * Improve sync of files with special characters

1.2.2 / 2020-10-20
==================

  * Fix default batch size for asset deletion

1.2.1 / 2020-10-20
==================

  * Fix `sync --pull` for files with extension in public id
  * Fix `sync --pull` for root folder

1.2.0 / 2020-10-16
==================

  * Add support for `--keep-unique` option in `sync`

1.1.1 / 2020-07-30
==================

  *  Fix dependencies versions

1.1.0 / 2020-07-23
==================

New functionality and features
------------------------------

  * Add support for Provisioning API
  * Add support for utility methods

Other Changes
-------------

  * Improve expression in `query_cld_folder`

1.0.7 / 2020-07-09
==================

  * Refactor path/public_id formatting
  * Normalize folder name when querying resources

1.0.6 / 2020-06-23
==================

  * Use upload_large when file size is larger than 20MB
  * Fix Windows path/public_id formatting
  * Update Windows configuration approach

1.0.5 / 2020-04-21
==================

  * Fix package installation issue
  * Fix unit tests
  * Fix package creation

1.0.4 / 2020-04-03
==================

  * Fix `url` command

1.0.3 / 2020-04-02
==================

  * Fix broken uploader commands

1.0.2 / 2020-04-01
==================

  * Fix sync pull command

1.0.0 / 2020-04-01
=============

  * Clean up and refactor code

0.4.2 / 2020-03-23
=============

New functionality and features
------------------------------

  * Add folder: prefix to Search API query in sync
  * Add Python installation information
  * Disable Windows color formatting
 
Other Changes
-------------

  * Update help and README
  * Fix sync pull
  * Fix populating templates with config
  * Remove specific dependency versions in requirements.txt
  * Remove some details and add links to the CLI documentation.
  * Update configuration via `os.environ.update` and `cloudinary.reset_config`
  * Improve PEP 8 compliance
  * Hotfix for pycloudinary 1.18.1 incompatibility
  * Update README and usage of various commands

0.3.0 / 2019-09-09
===================

New functionality and features
------------------------------

  * Add simple commands - `cld upload` instead of `cld uploader upload`
  * Improve PEP8 compliance
  * Fix csv generation
  * Add `--from_url` option for config
  * Add simple commands
  * Clean up file structure - move non-core modules to a new folder
  * Add csv report functionality for Search API
  * Add support of multi-threading 
  * Add `--save` for saving outputs
  * Add `sync` command
  * Add `migrate`, `auto-paginate` for admin api
  * Fix `-A` for search API
  * Add additional configuration feature
  * Add `auto-paginate` + `filter fields` option for Admin API
  * Migrate ls method into search
  * Add additional functionality
  * Add formatting
  * Add doc flags
  * Add filter fields
  * Add custom templates
  * Add User Agent
  * Add video player
  * Update template directory
  * Initial commit

 
Other Changes
-------------

  * Include pycloudinary version in user agent
  * Rename media library widget
