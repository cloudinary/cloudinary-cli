#!/usr/bin/env bash

# bump pycloudinary version to the latest release

set -e

function echo_err
{
    echo "$@" 1>&2;
}


# Intentionally make pushd silent
function pushd
{
    command pushd "$@" > /dev/null
}

# Intentionally make popd silent
function popd
{
    command popd > /dev/null
}


function verify_dependencies
{
    # Test if the gnu grep is installed
    if ! grep --version | grep -q GNU
    then
        echo_err "GNU grep is required for this script"
        echo_err "You can install it using the following command:"
        echo_err ""
        echo_err "brew install grep --with-default-names"
        return 1
    fi

    if [[ "${UPDATE_ONLY}" = true ]]; then
      return 0;
    fi
}

# Replace old string only if it is present in the file, otherwise return 1
function safe_replace
{
    local old=$1
    local new=$2
    local file=$3

    grep -q "${old}" "${file}" || { echo_err "${old} was not found in ${file}"; return 1; }

    ${CMD_PREFIX} sed -i.bak -e "${QUOTE}s/${old}/${new}/${QUOTE}" -- "${file}"  && rm -- "${file}.bak"
}

function get_latest_release
{
  curl --silent "https://api.github.com/repos/$1/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/'
}


function bump_pycloudinary_version
{
    # Enter git root
    pushd "$(git rev-parse --show-toplevel)"

    local NEW_VERSION
    NEW_VERSION=$(get_latest_release "cloudinary/pycloudinary")

    echo "$NEW_VERSION"

    for FILE in "setup.py" "requirements.txt"
    do
        safe_replace "cloudinary>=[a-zA-Z0-9\-\.]*" "cloudinary>=${NEW_VERSION}" $FILE|| return 1
    done

    popd
}
verify_dependencies
bump_pycloudinary_version
