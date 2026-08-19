import json
import re
import sys
import cloudinary.provisioning
from click import group, argument, option, echo, style, launch, BadParameter, ClickException
from cloudinary.exceptions import Error as CloudinaryError, RateLimited

from cloudinary_cli.defaults import (
    logger,
    ACCOUNT_EMAIL_PARAM,
    CLOUD_CLAIM_URL_PARAM,
    CLOUD_EXPIRES_AT_PARAM,
    CLOUD_DELIVERY_IPS_PARAM,
    CLOUD_ACCOUNT_ID_PARAM,
    CLOUD_EMAIL_PARAM,
    CLOUD_PLACEHOLDER_EMAIL_DOMAIN,
)
from cloudinary_cli.utils.api_utils import call_api
from cloudinary_cli.utils.json_utils import print_json
from cloudinary_cli.utils.utils import is_expired, prompt_user
from cloudinary_cli.utils.config_utils import (
    save_named_config,
    is_reserved_config_name,
    config_name_for_email,
    build_config_url,
    claim_url_from_url,
    claimable_cloud_names,
    expires_at_from_url,
    load_config,
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
If you are a human, or the human prefers to sign up themselves, use https://cloudinary.com/users/register_free instead.
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
        save_agent_config(_signup_environment(result), name=name, set_default=set_default,
                          params=_account_email_params(email))

    logger.info("Note: the account's credentials are inert until the emailed verification is completed.")


def _signup_environment(result):
    """The credentials block of a signup response, nested under product_environments[]."""
    return (result.get("product_environments") or [{}])[0]


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
    environment = _signup_environment(result)
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


def save_agent_config(credentials, name=None, set_default=False, params=None):
    """Persist a flat credentials dict ({cloud_name, api_key, api_secret}) as a named configuration,
    optionally carrying CLI-local metadata query params. On any failure it warns with the exact
    `cld config -n …` command to run by hand rather than raising. Returns the saved config name, or
    None when nothing was saved."""
    config_name = name or credentials.get("cloud_name")
    stored_url = _config_url_from_environment(credentials, params=params)
    if not stored_url or not config_name:
        logger.warning("Could not save the configuration automatically (missing credentials in the response). "
                       "Add it manually with `cld config -n <name> <CLOUDINARY_URL>`.")
        return None

    if name and name in user_config_names():
        logger.warning(f"Overwriting existing config '{name}'.")

    try:
        default_status = save_named_config(config_name, stored_url, set_default=set_default)
    except Exception as e:
        logger.warning(f"Could not save the configuration '{config_name}': {e}. "
                       f"Add it manually with `cld config -n {config_name} {_config_url_from_environment(credentials, params=params)}`.")
        return None

    logger.info(f"Config '{config_name}' saved!")
    logger.info(f"Example usage: cld -C {config_name} <command>")
    if default_status == "made":
        logger.info(f"Default set to '{config_name}'. Run `cld <command>` to use it, "
                    f"or `cld -C {config_name} <command>` to select it explicitly.")
    return config_name


def _config_url_from_environment(credentials, params=None):
    """Build a validated cloudinary:// config URL from a flat credentials dict, optionally carrying
    CLI-local metadata query params. Returns "" when the response lacks the credentials."""
    try:
        return build_config_url(credentials["cloud_name"], params=params or None,
                                api_key=credentials["api_key"], api_secret=credentials["api_secret"])
    except (KeyError, ValueError):
        return ""


def _account_email_params(email):
    """The saved-URL params recording a verified signup email."""
    return {ACCOUNT_EMAIL_PARAM: email.strip().lower()} if email and email.strip() else {}


@agent_group.group("cloud", help="Create and claim Claimable Clouds (for AI agents acting on behalf of a human).")
def cloud_group():
    pass


@cloud_group.command("create",
                     short_help="Provision a Claimable Cloud with immediately working credentials.",
                     help="""\b
Create a Claimable Cloud: a temporary cloud whose credentials work immediately, with no signup and
no verification email. Media delivery is locked to an IP allow-list (by default the address this
request comes from), and the cloud is disabled in about 24 hours unless a human claims it via
`cld agent cloud claim`, which makes it permanent and lifts the IP lock.
The cloud is saved as a named configuration (use --no-save to skip), along with the claim URL,
which the server returns exactly once and cannot be looked up again.
Note the IP allow-list restricts media delivery only - the Upload and Admin APIs authenticate by
signature and ignore it, so it is not a confidentiality control.
The optional EMAIL only pre-fills the claim page: it is never verified, no mail is sent to it at
creation, and it must be a real unused address - the server rejects taken and disposable domains.
Format: cld agent cloud create [EMAIL]
\te.g. cld agent cloud create you@example.com --claim
""")
@option("--ip", "ips", multiple=True,
        help="Additional IP permitted to deliver media, repeatable. Omit to let the server detect this "
             "request's own address. The literal 'requester_ip' means that address.")
@argument("email", required=False)
@option("--agent-framework", "agent_framework", help="The agent framework creating the cloud.")
@option("--agent-llm-model", "agent_llm_model", help="The LLM model powering the agent.")
@option("--agent-goal", "agent_goal", help="A short description of what the agent is trying to achieve.")
@option("--sdk-framework", "sdk_framework", help="The Cloudinary SDK framework the agent intends to use.")
@option("--name", help="Name for the saved configuration (default: the returned cloud name).")
@option("--set-default", "set_default", is_flag=True, help="Set the saved configuration as the default.")
@option("--no-save", "no_save", is_flag=True, help="Do not save the returned credentials as a configuration.")
@option("--claim", "claim_now", is_flag=True, help="Open the claim page as soon as the cloud is created.")
@option("--json", "as_json", is_flag=True,
        help="Output the full raw JSON response (agent contract) instead of the human summary.")
def cloud_create(ips, email, agent_framework, agent_llm_model, agent_goal, sdk_framework, name, set_default,
                 no_save, claim_now, as_json):
    ips = list(ips)
    if name and is_reserved_config_name(name):
        raise BadParameter(f"'{name}' is a reserved configuration name.")

    if not no_save:
        _refuse_config_collision(name)

    try:
        result = call_api(cloudinary.provisioning.create_cloud, delivery_ips=ips or None, email=email,
                          agent_framework=agent_framework, agent_llm_model=agent_llm_model,
                          agent_goal=agent_goal, sdk_framework=sdk_framework)
    except RateLimited as e:
        raise ClickException(f"Rate limited while creating the cloud: {e}. This endpoint is limited per IP "
                             f"address (about 10 clouds per 24 hours); wait a bit and try again.")
    except CloudinaryError as e:
        raise ClickException(_cloud_error_message(e))

    if as_json:
        print_json(result)
    else:
        _print_cloud_summary(result)

    saved_name = None
    if no_save:
        logger.warning("Nothing was saved (--no-save), so `cld agent cloud claim` cannot open the claim page "
                       "later. The claim URL above is the only way to keep this cloud - store it now.")
    else:
        saved_name = save_agent_config(result, name=name, set_default=set_default, params=_cloud_params(result))

    if claim_now:
        _open_claim_url(result.get("claim_url"), result.get("cloud_name"), print_only=False)
    elif saved_name:
        logger.info(f"Claim it with `cld agent cloud claim {saved_name}` - a human must finish in a browser.")


@cloud_group.command("claim",
                     short_help="Open the claim page for a saved Claimable Cloud.",
                     help="""\b
Open the claim page of a Claimable Cloud saved by `cld agent cloud create`, using the claim URL
stored with the configuration - the server returns it exactly once and there is no way to look it
up again. Run without a name to choose from the saved Claimable Clouds.
Claiming is a human action completed in a browser: they enter an email address, then click a link
sent to it. This command only opens (or prints) the page - it cannot claim anything itself, and
nothing reports whether a claim succeeded.
\te.g. cld agent cloud claim mycloud --print
""")
@argument("name", required=False)
@option("--print", "--no-open", "print_only", is_flag=True,
        help="Print the claim URL instead of opening a browser. Required for headless and agent use.")
@option("--json", "as_json", is_flag=True, help="Output {cloud_name, claim_url, expires_at} as JSON.")
def cloud_claim(name, print_only, as_json):
    if not name:
        name = _select_claimable_cloud()
        if name is None:
            return

    config_url = _saved_config_url(name)
    claim_url = claim_url_from_url(config_url)
    if not claim_url:
        raise ClickException(
            f"No claim URL is stored with the configuration '{name}'. It is returned only when the cloud is "
            f"created and cannot be re-fetched, so a cloud saved before this feature - or created outside "
            f"the CLI - cannot be claimed from here. Create a new one with `cld agent cloud create`.")

    expires_at = expires_at_from_url(config_url)
    if as_json:
        print_json({"cloud_name": _cloud_name_for_config(config_url, name),
                    "claim_url": claim_url, "expires_at": expires_at})
    _warn_if_expired(expires_at)
    # --json is the machine-readable contract: it already carries the claim URL, so never also
    # spawn a browser on the caller's behalf.
    _open_claim_url(claim_url, name, print_only=print_only or as_json, quiet=as_json)


def _refuse_config_collision(name):
    """Refuse a create that would overwrite an existing config, before any network call."""
    if name and name in user_config_names():
        raise ClickException(f"A configuration named '{name}' already exists. Choose another name with --name, "
                             f"or use --no-save to print the credentials without saving them.")


def _cloud_params(result):
    """The CLI-local metadata stored on a Claimable Cloud's saved config URL."""
    params = {key: result[key] for key in (CLOUD_CLAIM_URL_PARAM, CLOUD_EXPIRES_AT_PARAM,
                                           CLOUD_ACCOUNT_ID_PARAM) if result.get(key)}

    delivery_ips = result.get("delivery_ips")
    if delivery_ips:
        params[CLOUD_DELIVERY_IPS_PARAM] = ",".join(delivery_ips)

    email = (result.get("email") or "").strip()
    if email and not email.endswith(CLOUD_PLACEHOLDER_EMAIL_DOMAIN):
        params[CLOUD_EMAIL_PARAM] = email

    return params


# Response keys the Claimable Cloud summary renders explicitly (or omits, e.g. secrets folded into
# CLOUDINARY_URL). Anything else is surfaced generically by _extra_rows.
_KNOWN_CLOUD_KEYS = {"cloud_name", "api_key", "api_secret", "api_environment_variable", "delivery_ips",
                     "expires_at", "claim_url", "guidance"}


def _print_cloud_summary(result):
    rows = [
        ("Cloud name", result.get("cloud_name", "")),
        ("API key", result.get("api_key", "")),
        ("CLOUDINARY_URL", _config_url_from_environment(result)),
        ("Delivery IPs", ", ".join(result.get("delivery_ips") or [])),
    ]
    rows += _extra_rows(result, _KNOWN_CLOUD_KEYS)
    rows = [(label, value) for label, value in rows if value]

    echo(style("Claimable Cloud created. The credentials below work immediately.", fg="green"))
    if rows:
        width = max(len(label) for label, _ in rows) + 1
        template = "{0:" + str(width) + "} {1}"
        echo("\n".join(template.format(f"{label}:", value) for label, value in rows))

    expires_at = result.get("expires_at")
    claim_url = result.get("claim_url")
    if expires_at:
        echo(style(f"\nExpires at: {expires_at} (about 24h) - unclaimed clouds are disabled and their assets "
                   f"removed.", fg="yellow"))
    if claim_url:
        echo(style(f"Claim URL:  {claim_url}", fg="yellow"))
        echo("Opening it is the only way to keep this cloud. It is returned once and cannot be looked up "
             "again. A human must enter an email there and then click the link sent to it.")

    guidance = result.get("guidance")
    if guidance:
        echo(f"\n{guidance}")


def _cloud_error_message(error):
    """Actionable guidance for a create_cloud failure, recognised by the server's message text."""
    text = str(error)
    lowered = text.lower()

    if "rate limit" in lowered:
        return (f"Rate limited while creating the cloud: {text}. This endpoint is limited per IP address "
                f"(about 10 clouds per 24 hours); wait a bit and try again.")
    if "registration is currently unavailable" in lowered or "registration_disabled" in lowered:
        return f"Cloud provisioning is currently disabled by Cloudinary: {text}."
    if "location not permitted" in lowered:
        return (f"Could not create the cloud: {text}. This applies to the address the request comes from and "
                f"to every --ip supplied, so a delivery IP in a restricted country fails the whole call.")

    detail = _parse_error_detail(text)
    return f"Could not create the cloud: {detail}." if detail else f"Could not create the cloud: {text}."


def _saved_config_url(name):
    """The URL of the named saved config."""
    cfg = load_config()
    if name not in user_config_names(cfg):
        raise ClickException(f"Config {name} does not exist")
    return cfg[name]


def _select_claimable_cloud():
    """Pick a saved Claimable Cloud to claim when no name was given, or None when there is nothing to
    do."""
    names = claimable_cloud_names(include_expired=False)
    if not names:
        if claimable_cloud_names():
            logger.info("Every saved Claimable Cloud has expired, so there is nothing left to claim. "
                        "Create one with `cld agent cloud create`, or name one explicitly to open its "
                        "claim page anyway.")
        else:
            logger.info("No saved Claimable Clouds to claim. Create one with `cld agent cloud create`.")
        return None
    if len(names) == 1:
        return names[0]

    echo("Saved Claimable Clouds:")
    for i, name in enumerate(names, start=1):
        echo(f"  {i}) {name}")

    choice = prompt_user(f"Select a cloud to claim [1-{len(names)}] (or Enter to cancel): ",
                         noninteractive_hint="Pass the configuration name directly: `cld agent cloud claim <name>`.")
    if choice is None:
        raise ClickException("No selection was made.")
    choice = choice.strip()
    if not choice:
        return None
    if not (choice.isdigit() and 1 <= int(choice) <= len(names)):
        raise ClickException(f"Invalid selection '{choice}'. Expected a number between 1 and {len(names)}.")
    return names[int(choice) - 1]


def _cloud_name_for_config(config_url, name):
    from cloudinary_cli.utils.config_utils import cloud_name_from_url
    return cloud_name_from_url(config_url) or name


def _warn_if_expired(expires_at):
    """Warn when the stored expiry has passed, without refusing."""
    if is_expired(expires_at):
        logger.warning(f"This cloud expired at {expires_at}, so it has most likely been disabled and its assets "
                       f"removed. Opening the claim page anyway; create a new cloud with "
                       f"`cld agent cloud create` if it no longer works.")


def _open_claim_url(claim_url, name, print_only, quiet=False):
    """Open the claim page, or print the URL when asked to or when not attached to a TTY."""
    if not claim_url:
        raise ClickException(f"No claim URL is available for '{name}'.")

    if print_only or not sys.stdout.isatty():
        if not quiet:
            echo(claim_url)
        return

    launch(claim_url)
    logger.info(f"Opened the claim page for '{name}' in your browser. Claiming is not complete yet: a human "
                f"must enter an email address there, then click the link sent to it.")
    logger.info(f"If the browser did not open, visit this URL to claim the cloud:\n{claim_url}")
