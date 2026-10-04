import os
import random
import re
import time
from functools import wraps
from pathlib import Path

import cloudinary
import cloudinary.api
from cloudinary import logger
from cloudinary_cli.utils.api_utils import query_cld_folder
from urllib3 import HTTPResponse, disable_warnings
from urllib3._collections import HTTPHeaderDict

# Many CLI tests mock the HTTP layer but still need a resolvable config to run; without one the
# command exits "No Cloudinary configuration found". Gate those tests on a config being present.
CONFIG_PRESENT = bool(cloudinary.config().cloud_name)
REQUIRES_CONFIG = "Requires a Cloudinary configuration (set CLOUDINARY_URL or a saved config)"

SUFFIX = os.environ.get('TRAVIS_JOB_ID') or random.randint(10000, 99999)

RESOURCES_DIR = Path.joinpath(Path(__file__).resolve().parent, "resources")
TEST_FILES_DIR = str(Path.joinpath(RESOURCES_DIR, "test_sync"))

try:
    # urllib3 2.x support
    # noinspection PyProtectedMember
    import urllib3._request_methods
    URLLIB3_REQUEST = "urllib3._request_methods.RequestMethods.request"
except ImportError:
    URLLIB3_REQUEST = "urllib3.request.RequestMethods.request"

disable_warnings()


def unique_suffix(value):
    return f"{value}_{SUFFIX}"


def http_response_mock(body="", headers=None, status=200):
    if headers is None:
        headers = {}

    body = body.encode("UTF-8")

    return HTTPResponse(body, HTTPHeaderDict(headers), status=status)


def api_response_mock():
    return http_response_mock('{"foo":"bar"}', {"x-featureratelimit-limit": '0',
                                                "x-featureratelimit-reset": 'Sat, 01 Apr 2017 22:00:00 GMT',
                                                "x-featureratelimit-remaining": '0'})


def uploader_response_mock():
    return http_response_mock('''{
      "public_id": "mocked_file_id.bin",
      "resource_type": "raw",
      "type": "upload",
      "format":"bin",
      "foo": "bar",
      "resources": []
    }''')


def get_request_url(mocker):
    return mocker.call_args[1]["url"]


def get_params(mocker):
    """
    Extracts query parameters from mocked urllib3.request `fields` param.
    Supports both list and dict values of `fields`. Returns params as dictionary.
    Supports two list params formats:
      - {"urls[0]": "http://host1", "urls[1]": "http://host2"}
      - [("urls[]", "http://host1"), ("urls[]", "http://host2")]
    In both cases the result would be {"urls": ["http://host1", "http://host2"]}
    """

    if not mocker.call_args[1].get("fields"):
        return {}
    params = {}
    reg = re.compile(r'^(.*)\[\d*]$')
    fields = mocker.call_args[1].get("fields")
    fields = fields.items() if isinstance(fields, dict) else fields
    for k, v in fields:
        match = reg.match(k)
        if match:
            name = match.group(1)
            if name not in params:
                params[name] = []
            params[name].append(v)
        else:
            params[k] = v
    return params


def retry_assertion(func=None, *, num_tries=3, delay=3):
    """
    Helper for retrying inconsistent unit tests, running tearDown and setUp between tries

    :param func: The test method, when used without parentheses
    :param num_tries: Number of tries to perform
    :param delay: Delay in seconds between retries
    """
    if func is None:
        return lambda f: retry_assertion(f, num_tries=num_tries, delay=delay)

    @wraps(func)
    def retry_func(self, *args, **kwargs):
        for try_num in range(1, num_tries):
            try:
                return func(self, *args, **kwargs)
            except AssertionError:
                logger.warning(f"Assertion #{try_num} out of {num_tries} failed, retrying in {delay} seconds")
                self.tearDown()
                time.sleep(delay)
                self.setUp()

        return func(self, *args, **kwargs)

    return retry_func


def _asset_folder_resources(folder):
    resources = []
    options = {"max_results": 500}
    try:
        while True:
            res = cloudinary.api.resources_by_asset_folder(folder, **options)
            resources += res["resources"]
            if not res.get("next_cursor"):
                break
            options["next_cursor"] = res["next_cursor"]
        subfolders = cloudinary.api.subfolders(folder)["folders"]
    except cloudinary.exceptions.NotFound:
        return resources

    for subfolder in subfolders:
        resources += _asset_folder_resources(subfolder["path"])

    return resources


def _delete_assets(assets):
    for resource_type in {a["resource_type"] for a in assets}:
        public_ids = [a["public_id"] for a in assets if a["resource_type"] == resource_type]
        for batch in range(0, len(public_ids), 100):
            cloudinary.api.delete_resources(public_ids[batch:batch + 100], resource_type=resource_type)


def delete_cld_folder_if_exists(folder, folder_mode = "fixed"):
    if folder_mode == "fixed":
        for resource_type in ("image", "raw", "video"):
            cloudinary.api.delete_resources_by_prefix(folder, resource_type=resource_type)
    else:
        _delete_assets(list(query_cld_folder(folder, folder_mode).values()))

    try:
        cloudinary.api.delete_folder(folder)
    except cloudinary.exceptions.NotFound:
        pass
    except cloudinary.exceptions.BadRequest:
        if folder_mode == "fixed":
            raise
        _delete_assets(_asset_folder_resources(folder))
        cloudinary.api.delete_folder(folder)
