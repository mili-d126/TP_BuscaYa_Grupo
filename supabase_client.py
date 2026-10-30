import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import session

load_dotenv()


class SupabaseError(Exception):
    def __init__(self, status, message, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


class SessionExpiredError(Exception):
    pass


def _configuration():
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = (os.getenv("SUPABASE_PUBLISHABLE_KEY")
           or os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"))
    if not url or not key:
        raise RuntimeError(
            "Set NEXT_PUBLIC_SUPABASE_URL and "
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY in the environment."
        )
    return url.rstrip("/"), key


def _request(path, method="GET", params=None, payload=None, raw_body=None,
             content_type=None, access_token=None, extra_headers=None):
    base_url, publishable_key = _configuration()
    url = f"{base_url}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params, doseq=True)}"

    headers = {
        "apikey": publishable_key,
        "Authorization": f"Bearer {access_token or publishable_key}",
    }
    if payload is not None:
        raw_body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)

    request = Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
    except HTTPError as error:
        body = error.read()
        try:
            details = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        message = (details.get("msg") or details.get("message")
                   or details.get("error_description") or details.get("error")
                   or body.decode("utf-8", errors="replace")
                   or error.reason)
        raise SupabaseError(error.code, str(message), details.get("code")) from error

    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


def save_auth_session(auth_response):
    user = auth_response.get("user") or {}
    if user.get("id"):
        session["usuario_id"] = user["id"]
    if user.get("user_metadata", {}).get("nombre"):
        session["nombre"] = user["user_metadata"]["nombre"]
    if user.get("email"):
        session["email"] = user["email"]
    if auth_response.get("access_token"):
        session["supabase_access_token"] = auth_response["access_token"]
        session["supabase_refresh_token"] = auth_response.get("refresh_token")
        session["supabase_expires_at"] = auth_response.get(
            "expires_at", time.time() + auth_response.get("expires_in", 3600)
        )


def sign_up(email, password, name):
    response = _request(
        "auth/v1/signup",
        method="POST",
        payload={"email": email, "password": password, "data": {"nombre": name}},
    )
    if response.get("access_token"):
        save_auth_session(response)
    return response


def sign_in(email, password):
    response = _request(
        "auth/v1/token",
        method="POST",
        params={"grant_type": "password"},
        payload={"email": email, "password": password},
    )
    save_auth_session(response)
    return response


def _access_token():
    token = session.get("supabase_access_token")
    if not token:
        raise RuntimeError("The user is not authenticated with Supabase.")
    if session.get("supabase_expires_at", 0) > time.time() + 60:
        return token

    refresh_token = session.get("supabase_refresh_token")
    if not refresh_token:
        session.clear()
        raise SessionExpiredError("The Supabase session expired.")

    try:
        response = _request(
            "auth/v1/token",
            method="POST",
            params={"grant_type": "refresh_token"},
            payload={"refresh_token": refresh_token},
        )
    except SupabaseError as error:
        if error.status in (400, 401):
            session.clear()
            raise SessionExpiredError("The Supabase session expired.") from error
        raise
    save_auth_session(response)
    return session["supabase_access_token"]


def update_password(password, access_token=None):
    return _request(
        "auth/v1/user",
        method="PUT",
        payload={"password": password},
        access_token=access_token or _access_token(),
    )


def select(table, params):
    return _request(
        f"rest/v1/{table}", params=params, access_token=_access_token()
    )


def insert(table, values):
    return _request(
        f"rest/v1/{table}",
        method="POST",
        params={"select": "*"},
        payload=values,
        access_token=_access_token(),
        extra_headers={"Prefer": "return=representation"},
    )


def update(table, params, values):
    return _request(
        f"rest/v1/{table}",
        method="PATCH",
        params=params,
        payload=values,
        access_token=_access_token(),
        extra_headers={"Prefer": "return=representation"},
    )


def delete(table, params):
    return _request(
        f"rest/v1/{table}",
        method="DELETE",
        params=params,
        access_token=_access_token(),
        extra_headers={"Prefer": "return=representation"},
    )


def upload_report_photo(object_path, content, content_type):
    encoded_path = quote(object_path, safe="/")
    _request(
        f"storage/v1/object/report-photos/{encoded_path}",
        method="POST",
        raw_body=content,
        content_type=content_type,
        access_token=_access_token(),
        extra_headers={"x-upsert": "false"},
    )
    base_url, _ = _configuration()
    return f"{base_url}/storage/v1/object/public/report-photos/{encoded_path}"


def delete_report_photo(public_url):
    base_url, _ = _configuration()
    parsed_url = urlparse(public_url)
    prefix = "/storage/v1/object/public/report-photos/"
    base = urlparse(base_url)
    if parsed_url.netloc != base.netloc or not parsed_url.path.startswith(prefix):
        return
    object_path = parsed_url.path[len(prefix):]
    _request(
        f"storage/v1/object/report-photos/{quote(object_path, safe='/')}",
        method="DELETE",
        payload={"prefixes": [object_path]},
        access_token=_access_token(),
    )
