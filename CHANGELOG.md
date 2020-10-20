
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
