import os
import random
import re
import time
from functools import wraps
from pathlib import Path

import cloudinary.api
from cloudinary import logger
from urllib3 import HTTPResponse, disable_warnings
from urllib3._collections import HTTPHeaderDict

SUFFIX = os.environ.get('TRAVIS_JOB_ID') or random.randint(10000, 99999)

RESOURCES_DIR = Path.joinpath(Path(__file__).resolve().parent, "resources")
TEST_FILES_DIR = str(Path.joinpath(RESOURCES_DIR, "test_sync"))

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
      "foo": "bar"
    }''')


def get_request_url(mocker):
    return mocker.call_args[0][1]


def get_params(mocker):
    """
    Extracts query parameters from mocked urllib3.request `fields` param.
    Supports both list and dict values of `fields`. Returns params as dictionary.
    Supports two list params formats:
      - {"urls[0]": "http://host1", "urls[1]": "http://host2"}
      - [("urls[]", "http://host1"), ("urls[]", "http://host2")]
    In both cases the result would be {"urls": ["http://host1", "http://host2"]}
    """

    args = mocker.call_args[0]
    if not args or not args[2]:
        return {}
    params = {}
    reg = re.compile(r'^(.*)\[\d*]$')
    fields = args[2].items() if isinstance(args[2], dict) else args[2]
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


def retry_assertion(num_tries=3, delay=3):
    """
    Helper for retrying inconsistent unit tests

    :param num_tries: Number of tries to perform
    :param delay: Delay in seconds between retries
    """

    def retry_decorator(func):
        @wraps(func)
        def retry_func(*args, **kwargs):
            try_num = 1
            while try_num < num_tries:
                try:
                    return func(*args, **kwargs)
                except AssertionError:
                    logger.warning("Assertion #{} out of {} failed, retrying in {} seconds".format(try_num, num_tries,
                                                                                                   delay))
                    time.sleep(delay)
                    try_num += 1

            return func(*args, **kwargs)

        return retry_func

    return retry_decorator


def delete_cld_folder_if_exists(folder):
    cloudinary.api.delete_resources_by_prefix(folder)
    try:
        cloudinary.api.delete_folder(folder)
    except cloudinary.exceptions.NotFound:
        pass
