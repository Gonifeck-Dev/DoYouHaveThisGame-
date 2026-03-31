from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import requests


class SteamApiError(RuntimeError):
    """Raised when Steam Web API returns an error or invalid payload."""


def normalize_string(value: Any) -> Optional[str]:
    """Convert common API values to non-empty strings."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def deep_find_first(data: Any, target_keys: Set[str]) -> Any:
    """Find the first non-empty value for any key in nested JSON payloads."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in target_keys and value not in (None, ""):
                return value
        for value in data.values():
            found = deep_find_first(value, target_keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = deep_find_first(item, target_keys)
            if found is not None:
                return found
    return None


class SteamApiClient:
    BASE_URL = "https://api.steampowered.com"

    def __init__(self, api_key: Optional[str], timeout: int = 30) -> None:
        self.api_key = normalize_string(api_key)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "steam-api-cli/1.0"})

    def request(
        self,
        interface: str,
        method_name: str,
        version: str = "v1",
        params: Optional[Dict[str, Any]] = None,
        http_method: str = "GET",
        include_api_key: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{interface}/{method_name}/{version}/"
        clean_params: Dict[str, Any] = {}

        if params:
            for key, value in params.items():
                if value is None:
                    continue
                clean_params[key] = value

        if include_api_key and self.api_key and "key" not in clean_params and "access_token" not in clean_params:
            clean_params["key"] = self.api_key

        method_upper = http_method.upper()
        try:
            if method_upper == "POST":
                response = self.session.post(url, data=clean_params, timeout=self.timeout)
            else:
                response = self.session.get(url, params=clean_params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SteamApiError(f"Request error for {interface}/{method_name}: {exc}") from exc

        if not response.ok:
            message = response.text[:400].replace("\n", " ")
            raise SteamApiError(
                f"Steam API error {response.status_code} for {interface}/{method_name}: {message}"
            )

        try:
            payload: Dict[str, Any] = response.json()
        except ValueError as exc:
            raise SteamApiError(f"Non-JSON response for {interface}/{method_name}") from exc

        return payload

    def get_store_async_config(self, steam_login_secure: Optional[str] = None) -> Dict[str, Any]:
        """Request store async config endpoint used by Steam web to expose webapi_token."""
        url = "https://store.steampowered.com/pointssummary/ajaxgetasyncconfig"
        cookies: Dict[str, str] = {}
        if steam_login_secure:
            cookies["steamLoginSecure"] = steam_login_secure

        try:
            response = self.session.get(url, cookies=cookies, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SteamApiError(f"Request error for store async config: {exc}") from exc

        if not response.ok:
            message = response.text[:400].replace("\n", " ")
            raise SteamApiError(
                f"Store endpoint error {response.status_code} for ajaxgetasyncconfig: {message}"
            )

        try:
            payload: Dict[str, Any] = response.json()
        except ValueError as exc:
            raise SteamApiError("Non-JSON response for store async config") from exc

        return payload

    def generate_access_token_for_app(
        self, refresh_token: str, steamid: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.request(
            interface="IAuthenticationService",
            method_name="GenerateAccessTokenForApp",
            version="v1",
            params={"refresh_token": refresh_token, "steamid": steamid},
            http_method="POST",
        )

    def get_token_details(self, access_token: str) -> Dict[str, Any]:
        return self.request(
            interface="ISteamUserOAuth",
            method_name="GetTokenDetails",
            version="v1",
            params={"access_token": access_token},
            http_method="GET",
        )

    def resolve_vanity_url(self, vanity_url: str) -> Dict[str, Any]:
        return self.request(
            interface="ISteamUser",
            method_name="ResolveVanityURL",
            version="v1",
            params={"vanityurl": vanity_url},
            http_method="GET",
        )

    def get_family_group_for_user(
        self,
        steamid: Optional[str] = None,
        include_family_group_response: bool = False,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        access_token = normalize_string(access_token)
        return self.request(
            interface="IFamilyGroupsService",
            method_name="GetFamilyGroupForUser",
            version="v1",
            params={
                "steamid": steamid,
                "include_family_group_response": int(include_family_group_response),
                "access_token": access_token,
            },
            http_method="GET",
            include_api_key=not bool(access_token),
        )

    def get_shared_library_apps(
        self,
        access_token: str,
        steamid: str,
        family_groupid: str,
        include_own: bool = True,
    ) -> Dict[str, Any]:
        return self.request(
            interface="IFamilyGroupsService",
            method_name="GetSharedLibraryApps",
            version="v1",
            params={
                "access_token": access_token,
                "include_own": str(include_own).lower(),
                "steamid": steamid,
                "family_groupid": family_groupid,
            },
            http_method="GET",
            include_api_key=False,
        )

    def get_owned_games(
        self,
        steamid: str,
        include_appinfo: bool = True,
        include_played_free_games: bool = True,
    ) -> Dict[str, Any]:
        """Get all games owned by a Steam user. Profile must be public."""
        return self.request(
            interface="IPlayerService",
            method_name="GetOwnedGames",
            version="v1",
            params={
                "steamid": steamid,
                "include_appinfo": int(include_appinfo),
                "include_played_free_games": int(include_played_free_games),
            },
            http_method="GET",
        )

    def get_steamspy_app_details(self, appid: str) -> Dict[str, Any]:
        """Fetch app details from SteamSpy (no auth required). Returns 'tags' as {tag: votes}."""
        url = "https://steamspy.com/api.php"
        try:
            response = self.session.get(
                url,
                params={"request": "appdetails", "appid": appid},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SteamApiError(f"SteamSpy request error for appid {appid}: {exc}") from exc
        if not response.ok:
            raise SteamApiError(f"SteamSpy error {response.status_code} for appid {appid}")
        try:
            return response.json()
        except ValueError as exc:
            raise SteamApiError(f"Non-JSON SteamSpy response for appid {appid}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Get access_token, steamid and family_groupid using Steam Web API endpoints."
    )
    parser.add_argument("--api-key", default=os.getenv("STEAM_API_KEY"), help="Steam Web API key")
    parser.add_argument(
        "--refresh-token",
        default=os.getenv("STEAM_REFRESH_TOKEN"),
        help="Refresh token to generate a new access_token",
    )
    parser.add_argument(
        "--access-token",
        default=os.getenv("STEAM_ACCESS_TOKEN"),
        help="OAuth access token",
    )
    parser.add_argument("--steamid", default=os.getenv("STEAM_STEAMID"), help="64-bit SteamID")
    parser.add_argument(
        "--vanity-url",
        default=os.getenv("STEAM_VANITY_URL"),
        help="Steam vanity profile name to resolve into steamid",
    )
    parser.add_argument(
        "--include-family-response",
        action="store_true",
        help="Ask GetFamilyGroupForUser to include extra family group data",
    )
    parser.add_argument(
        "--skip-family",
        action="store_true",
        help="Skip family_groupid request",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--debug", action="store_true", help="Print raw endpoint payloads to stderr")
    return parser.parse_args()


def fetch_steam_info(
    api_key: Optional[str] = None,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    steamid: Optional[str] = None,
    vanity_url: Optional[str] = None,
    include_family_response: bool = False,
    skip_family: bool = False,
    timeout: int = 30,
) -> Tuple[Dict[str, Optional[str]], Dict[str, Any], List[str]]:
    """Resolve access_token, steamid and family_groupid using known Steam endpoints."""
    api_key = normalize_string(api_key)
    refresh_token = normalize_string(refresh_token)
    access_token = normalize_string(access_token)
    steamid = normalize_string(steamid)
    vanity_url = normalize_string(vanity_url)

    payloads: Dict[str, Any] = {}
    warnings: List[str] = []
    client = SteamApiClient(api_key=api_key, timeout=timeout)

    if not steamid and vanity_url:
        if not api_key:
            raise SteamApiError("ResolveVanityURL requires --api-key")
        payloads["resolve_vanity"] = client.resolve_vanity_url(vanity_url)
        steamid = normalize_string(deep_find_first(payloads["resolve_vanity"], {"steamid"}))

    if not access_token and refresh_token:
        if not api_key:
            raise SteamApiError("GenerateAccessTokenForApp requires --api-key")
        payloads["generate_access_token"] = client.generate_access_token_for_app(
            refresh_token=refresh_token,
            steamid=steamid,
        )
        access_token = normalize_string(
            deep_find_first(payloads["generate_access_token"], {"access_token"})
        )
        if not steamid:
            steamid = normalize_string(
                deep_find_first(payloads["generate_access_token"], {"steamid"})
            )

    if not steamid and access_token:
        payloads["token_details"] = client.get_token_details(access_token)
        steamid = normalize_string(deep_find_first(payloads["token_details"], {"steamid"}))

    family_groupid: Optional[str] = None
    if not skip_family:
        if not access_token and not api_key:
            raise SteamApiError("GetFamilyGroupForUser requires --access-token or --api-key")
        payloads["family_group"] = client.get_family_group_for_user(
            steamid=steamid,
            include_family_group_response=include_family_response,
            access_token=access_token,
        )
        family_groupid = normalize_string(
            deep_find_first(
                payloads["family_group"],
                {"family_groupid", "family_group_id", "gidfamily", "familyid", "groupid"},
            )
        )

    result = {
        "access_token": access_token,
        "steamid": steamid,
        "family_groupid": family_groupid,
    }

    if not result["access_token"]:
        warnings.append("access_token was not found. Provide --access-token or --refresh-token.")
    if not result["steamid"]:
        warnings.append("steamid was not found. Provide --steamid, --vanity-url, or --access-token.")

    return result, payloads, warnings


def main() -> int:
    args = parse_args()

    try:
        result, payloads, warnings = fetch_steam_info(
            api_key=args.api_key,
            refresh_token=args.refresh_token,
            access_token=args.access_token,
            steamid=args.steamid,
            vanity_url=args.vanity_url,
            include_family_response=args.include_family_response,
            skip_family=args.skip_family,
            timeout=args.timeout,
        )
        print(json.dumps(result, indent=2, ensure_ascii=True))

        if args.debug:
            print("\n# debug_payloads", file=sys.stderr)
            print(json.dumps(payloads, indent=2, ensure_ascii=True), file=sys.stderr)

        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)

        return 0

    except SteamApiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
