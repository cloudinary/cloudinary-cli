import json
import re

import cloudinary.provisioning
from click import group, argument, option, echo, style, BadParameter, ClickException
from cloudinary.exceptions import Error as CloudinaryError, RateLimited

from cloudinary_cli.defaults import logger, ACCOUNT_EMAIL_PARAM
from cloudinary_cli.utils.api_utils import call_api
from cloudinary_cli.utils.json_utils import print_json
from cloudinary_cli.utils.config_utils import (
    save_named_config,
    is_reserved_config_name,
    config_name_for_email,
    build_config_url,
    user_config_names,
    config_optional,
)


@config_optional
@group("agent", help="Commands for AI agents acting on behalf of a human.")
def agent_group():
    pass


@agent_group.command("signup",
               short_help="Create a Cloudinary account on behalf of a human (for AI agents only).",
               help="""\b
For AI agents only: create a Free-plan Cloudinary account on behalf of a human.
A verification email is sent to the address; the credentials are inert until the human verifies it.
The returned product environment is saved as a named configuration (use --no-save to skip).
Format: cld agent signup <email> <agent_framework> <agent_llm_model> <agent_goal>
\te.g. cld agent signup you@example.com claude-code claude-fable-5 "test the agent account flow"
""")
@argument("email")
@argument("agent_framework")
@argument("agent_llm_model")
@argument("agent_goal")
@option("--sdk-framework", "sdk_framework", help="The Cloudinary SDK framework the agent intends to use.")
@option("--name", help="Name for the saved configuration (default: the returned cloud name).")
@option("--set-default", "set_default", is_flag=True, help="Set the saved configuration as the default.")
@option("--no-save", "no_save", is_flag=True, help="Do not save the returned credentials as a configuration.")
@option("--json", "as_json", is_flag=True,
        help="Output the full raw JSON response (agent contract) instead of the human summary.")
def signup(email, agent_framework, agent_llm_model, agent_goal, sdk_framework, name, set_default, no_save,
           as_json):
    if name and is_reserved_config_name(name):
        raise BadParameter(f"'{name}' is a reserved configuration name.")
    if not email or not email.strip():
        raise BadParameter("email must not be empty.")

    existing = config_name_for_email(email)
    if existing:
        raise ClickException(_already_have_config_message(email, existing))

    try:
        result = call_api(cloudinary.provisioning.create_agent_account, email, agent_framework,
                          agent_llm_model, agent_goal, sdk_framework=sdk_framework)
    except RateLimited as e:
        raise ClickException(
            f"Rate limited while creating the account: {e}. This endpoint is limited per IP address; "
            f"wait a bit and try again.")
    except CloudinaryError as e:
        raise ClickException(_signup_error_message(email, e))

    # Show the freshly-minted credentials BEFORE saving, so a save failure can never lose them.
    if as_json:
        print_json(result)
    else:
        _print_signup_summary(result)

    if not no_save:
        save_agent_config(result, email, name=name, set_default=set_default)

    logger.info("Note: the account's credentials are inert until the emailed verification is completed.")


def _already_have_config_message(email, name):
    return (f"You already signed up with {email} (saved as '{name}'). "
            f"Use it with `cld -C {name} <command>`. "
            f"If it's not activated yet, complete the verification email; or run `cld login` if you use OAuth.")


def _account_exists_message(email):
    return (f"An account already exists for {email}, but no configuration is saved on this machine. "
            f"If it's already verified, add its CLOUDINARY_URL with `cld config -n <name> <url>` "
            f"(or `cld login` if you use OAuth). If you just created it, complete the verification email first.")


def _signup_error_message(email, error):
    text = str(error)
    if "has already been taken" in text or "409" in text:
        return _account_exists_message(email)

    detail = _parse_error_detail(text)
    return f"Signup failed: {detail}." if detail else f"Signup failed: {text}."


def _parse_error_detail(text):
    """Best-effort human message from a provisioning error string like
    'Error 400 - {"email":["is invalid"]}' or '... {"error":{"message":"boom"}}'. Returns None on any
    failure so the caller falls back to the raw text."""
    match = re.search(r"\{.*\}", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None

    error = payload.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])

    parts = []
    for field, msgs in payload.items():
        msgs = msgs if isinstance(msgs, list) else [msgs]
        parts.append(f"{field} {', '.join(str(m) for m in msgs)}")
    return "; ".join(parts) or None


# Top-level and product-environment response keys the summary renders explicitly (or deliberately
# omits, e.g. secrets folded into CLOUDINARY_URL). Any key NOT listed here is surfaced generically
# by _extra_rows so future fields the server adds are never silently dropped.
_KNOWN_TOP_LEVEL_KEYS = {"email", "plan_name", "product_environments", "guidance"}
_KNOWN_ENV_KEYS = {"cloud_name", "api_key", "api_secret", "api_environment_variable", "external_id"}


def _print_signup_summary(result):
    environment = (result.get("product_environments") or [{}])[0]
    rows = [
        ("Email", result.get("email", "")),
        ("Plan", result.get("plan_name", "")),
        ("Cloud name", environment.get("cloud_name", "")),
        ("API key", environment.get("api_key", "")),
        ("CLOUDINARY_URL", _config_url_from_environment(environment)),
    ]
    rows += _extra_rows(result, _KNOWN_TOP_LEVEL_KEYS)
    rows += _extra_rows(environment, _KNOWN_ENV_KEYS)
    rows = [(label, value) for label, value in rows if value]

    echo(style("Cloudinary account created.", fg="green"))
    if rows:
        width = max(len(label) for label, _ in rows) + 1
        template = "{0:" + str(width) + "} {1}"
        echo("\n".join(template.format(f"{label}:", value) for label, value in rows))

    guidance = result.get("guidance")
    if guidance:
        echo(f"\n{guidance}")


def _extra_rows(data, known_keys):
    """(label, value) rows for scalar keys not already rendered, so response fields the server adds
    in the future surface instead of being dropped. Skips nested dict/list values (shown elsewhere
    or via --json) and empties."""
    rows = []
    for key, value in data.items():
        if key in known_keys or isinstance(value, (dict, list)) or value in (None, ""):
            continue
        rows.append((key.replace("_", " ").capitalize(), value))
    return rows


def save_agent_config(result, email, name=None, set_default=False):
    environment = (result.get("product_environments") or [{}])[0]
    config_name = name or environment.get("cloud_name")
    stored_url = _config_url_from_environment(environment, email=email)
    if not stored_url or not config_name:
        logger.warning("Could not save the configuration automatically (missing credentials in the response). "
                       "Add it manually with `cld config -n <name> <CLOUDINARY_URL>`.")
        return

    if name and name in user_config_names():
        logger.warning(f"Overwriting existing config '{name}'.")

    try:
        default_status = save_named_config(config_name, stored_url, set_default=set_default)
    except Exception as e:
        logger.warning(f"Could not save the configuration '{config_name}': {e}. "
                       f"Add it manually with `cld config -n {config_name} {_config_url_from_environment(environment)}`.")
        return

    logger.info(f"Config '{config_name}' saved!")
    logger.info(f"Example usage: cld -C {config_name} <command>")
    if default_status == "made":
        logger.info(f"Default set to '{config_name}'. Run `cld <command>` to use it, "
                    f"or `cld -C {config_name} <command>` to select it explicitly.")


def _config_url_from_environment(environment, email=None):
    """Build a validated cloudinary:// config URL from a product-environment's credential fields,
    optionally carrying the account email. Returns "" when the response lacks the credentials."""
    params = {ACCOUNT_EMAIL_PARAM: email.strip().lower()} if email and email.strip() else None
    try:
        return build_config_url(environment["cloud_name"], params=params,
                                api_key=environment["api_key"], api_secret=environment["api_secret"])
    except (KeyError, ValueError):
        return ""
