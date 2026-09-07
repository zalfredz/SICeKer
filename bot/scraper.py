"""Authenticated, persistent HTTP client for SCELE."""

from __future__ import annotations

from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

CALENDAR_URL = "https://scele.cs.ui.ac.id/calendar/view.php?view=upcoming"
LOGIN_URL = "https://scele.cs.ui.ac.id/login/index.php"


class SceleError(RuntimeError):
    pass


class SceleAuthenticationError(SceleError):
    pass


class SceleClient:
    def __init__(self, username: str | None = None, password: str | None = None) -> None:
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "scele-discord-notifier/1.0"})

    @staticmethod
    def _is_login_response(response: requests.Response) -> bool:
        path = urlparse(response.url).path.lower()
        return "/login/" in path or 'name="username"' in response.text.lower()

    def _login(self) -> None:
        if not self.username or not self.password:
            raise SceleAuthenticationError(
                "SCELE requires login. Set SCELE_USERNAME and SCELE_PASSWORD as GitHub Secrets."
            )
        try:
            page = self.session.get(LOGIN_URL, timeout=30)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "html.parser")
            token = soup.select_one("input[name='logintoken']")
            if not token or not token.get("value"):
                raise SceleAuthenticationError("SCELE login form did not contain logintoken.")
            response = self.session.post(
                LOGIN_URL,
                data={
                    "username": self.username,
                    "password": self.password,
                    "logintoken": token["value"],
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SceleError(f"Could not contact SCELE login: {exc}") from exc
        if self._is_login_response(response):
            raise SceleAuthenticationError(
                "SCELE login was not accepted. Check the credentials or an interactive login requirement."
            )

    def fetch_calendar(self) -> str:
        try:
            response = self.session.get(CALENDAR_URL, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SceleError(f"Could not fetch SCELE calendar: {exc}") from exc

        if self._is_login_response(response):
            self._login()
            try:
                response = self.session.get(CALENDAR_URL, timeout=30)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise SceleError(f"Could not fetch SCELE calendar after login: {exc}") from exc
            if self._is_login_response(response):
                raise SceleAuthenticationError("SCELE calendar is still unavailable after login.")
        return response.text
