import logging
import os
from os.path import join as path_join, expanduser, abspath, dirname

import click_log

logger = logging.getLogger(__name__)

click_log.basic_config(logger)

TEMPLATE_EXTS = {
    "python": "py",
    "html": "html",
    "ruby": "rb",
    "node": "js",
    "php": "php",
    "java": "java",
}

CLOUDINARY_HOME = os.environ.get('CLOUDINARY_HOME')

if CLOUDINARY_HOME is None:
    CLOUDINARY_HOME = abspath(path_join(expanduser("~"), ".cloudinary-cli"))

CLOUDINARY_CLI_CONFIG_FILE = abspath(path_join(CLOUDINARY_HOME, 'config.json'))

# OAuth (ORY Hydra) configuration for `cld login`. The region string derives both the API and
# OAuth hosts; an unknown region simply fails to resolve.
DEFAULT_REGION = 'api'


def normalize_region(region):
    # Bare geo codes ('eu') become 'api-<geo>'; 'api' and 'api-*' pass through.
    region = (region or DEFAULT_REGION).strip()
    return region if region.startswith('api') else f'api-{region}'


def _oauth_host_for(region):
    # Short suffixes (geo codes) use the central authz server; longer ones route to oauth-<suffix>.
    _, _, suffix = region.partition('-')
    return 'oauth.cloudinary.com' if len(suffix) <= 2 else f'oauth-{suffix}.cloudinary.com'


def api_host_for_region(region):
    return f'https://{normalize_region(region)}.cloudinary.com'


def oauth_base_url_for_region(region):
    return f'https://{_oauth_host_for(normalize_region(region))}'


def oauth_authorize_url_for_region(region):
    return f'{oauth_base_url_for_region(region)}/oauth2/auth'


def oauth_token_url_for_region(region):
    return f'{oauth_base_url_for_region(region)}/oauth2/token'


CLOUDINARY_REGION = normalize_region(os.environ.get('CLOUDINARY_REGION'))

# Public PKCE client (no secret).
OAUTH_CLIENT_ID = 'cld_cli'
OAUTH_SCOPES = 'openid offline_access asset_management upload'

# Hydra requires an exact redirect match, so the port is fixed and must match the registered client.
OAUTH_DEFAULT_REDIRECT_HOST = '127.0.0.1'
OAUTH_REDIRECT_HOST = os.environ.get('CLOUDINARY_OAUTH_REDIRECT_HOST', OAUTH_DEFAULT_REDIRECT_HOST)
OAUTH_DEFAULT_REDIRECT_PORT = 49421
OAUTH_REDIRECT_PORT = int(os.environ.get('CLOUDINARY_OAUTH_REDIRECT_PORT', OAUTH_DEFAULT_REDIRECT_PORT))
OAUTH_CALLBACK_PATH = '/callback'

OAUTH_CALLBACK_TIMEOUT_SECONDS = 300
OAUTH_EXPIRY_SKEW_SECONDS = 30
OAUTH_HTTP_TIMEOUT_SECONDS = 30
# Fallback when the token response omits expires_in, so it can't pin expires_at to "now".
OAUTH_FALLBACK_EXPIRES_IN_SECONDS = 3600

TEMPLATE_FOLDER_NAME = 'templates'
CLOUDINARY_CLI_ROOT = dirname(__file__)
TEMPLATE_FOLDER = path_join(CLOUDINARY_CLI_ROOT, TEMPLATE_FOLDER_NAME)
CUSTOM_TEMPLATE_FOLDER = path_join(abspath(CLOUDINARY_HOME), TEMPLATE_FOLDER_NAME)

OLD_CLOUDINARY_CLI_CONFIG_FILE = path_join(expanduser("~"), '.cloudinary-cli-config')
