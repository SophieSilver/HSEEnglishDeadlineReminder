"""
Getting the auth tokens for HSE authorization
"""
import httpx
import asyncio
from model import Token
import dateparser
from datetime import datetime, timedelta
import urllib.parse
from bs4 import BeautifulSoup

class AuthError(Exception):
    """
    Used for generalizing errors occuring during auth process
    """
    pass

class LMSAuther:
    # idk if client id ever changes
    FORM_URL = "https://auth.hse.ru/adfs/oauth2/authorize?client_id=4403a646-2af8-42ba-a2b1-4f5a50a5b376&redirect_uri=https://smartedu.hse.ru/auth&response_type=token&response_mode=fragment"
    HOST = "https://auth.hse.ru"

    # used to get the moodle session token
    OIDC_URL = "https://edu.hse.ru/auth/oidc/"
    
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def __get_auth_url(self) -> str:
        """
        Needed because request_id always changes
        """
        try:
            form_page = await self.client.get(self.FORM_URL)
            form_page.raise_for_status()
        except httpx.HTTPError as e:
            # re-raising exceptions as AuthErrors
            raise AuthError(f"{e}")

        # this would not raise anything even if garbage is given
        soup = BeautifulSoup(form_page.content, features="html.parser")

        form = soup.select_one("#loginForm")

        if form is None:
            raise (AuthError("Auth form not found"))

        auth_uri = form.attrs.get("action")

        if auth_uri is None:
            raise AuthError("Auth URI not found")

        return self.HOST + auth_uri


    async def __send_auth_form_data(self, url: str, username: str, password: str) -> httpx.Response:
        quoted_name = urllib.parse.quote_plus(username)
        quoted_pass = urllib.parse.quote_plus(password)
        payload = {
            "UserName": username,
            "Password": password,
            "Kmsi": True,
            "AuthMethod": "FormsAuthentication",
        }
        try:
            response = await self.client.post(url, data=payload)
        except httpx.HTTPError as e:
            raise AuthError(f"{e}")

        return response

    @staticmethod
    def __get_msis_from_response(response: httpx.Response) -> Token:
        # not using client.cookies because we need the expiration date
        set_cookie_header: str | None = response.headers.get("set-cookie")

        if set_cookie_header is None:
            raise AuthError("set-cookie header not found")

        cookie_data_list: list[tuple[str, str]] = [
            # gets cookie value and expiration date
            tuple(pair.split("=", 1))
            for pair in set_cookie_header.split(";")[:2]
        ]
        try:
            cookie_data = {key.strip(): value.strip() for key, value in cookie_data_list}
        except ValueError:
            raise AuthError("Couldn't parse cookie data")

        title = "MSISAuth"
        value = cookie_data.get(title)

        if value is None:
            raise AuthError("Couldn't get the bearer token value")

        # setting default to "" so we don't have to make another None check
        expires = dateparser.parse(cookie_data.get("expires", ""))

        if expires is None:
            raise AuthError("Couldn't get token expiration date")

        return Token(title=title, value=value, expiration_dt=expires)
    
    async def get_bearer_token(self, msisauth_token: Token) -> Token:
        title = msisauth_token.title
        value = msisauth_token.value

        # setting the auth cookie on the clien
        self.client.cookies.set(title, value)

        try:
            # this response should have a location header
            # which has an access_token parameter
            response = await self.client.get(self.FORM_URL)
        except httpx.HTTPError as e:
            raise AuthError(f"{e}")

        if response.status_code != 302:
            raise AuthError(f"Unexpected response status code: {response.status_code}")

        # extracting the access token from the url
        url_with_token: str = response.headers.get("location")
        # just to be safe, but if the status is 302 it should
        if url_with_token is None:
            raise AuthError(
                "Location not found in headers (Shouldn't see this, something's gone terribly wrong)"
            )

        frag_with_token = urllib.parse.urlparse(url_with_token).fragment
        frag_dict = urllib.parse.parse_qs(frag_with_token)
        # for some reason the dict values are lists idk why

        try:
            token_value = frag_dict["access_token"][0]
            # getting expiration date
            expires_in_secs = int(frag_dict["expires_in"][0])
        except KeyError:
            raise AuthError("Could not get the bearer token or its expiration date")

        expiration_dt = datetime.now() + timedelta(seconds=expires_in_secs)

        return Token(title="Bearer", value=token_value, expiration_dt=expiration_dt)

    async def get_msisauth_token(self, username: str, password: str) -> Token:
        auth_url = await self.__get_auth_url()
        auth_response = await self.__send_auth_form_data(auth_url, username, password)
        msisauth = self.__get_msis_from_response(auth_response)
        
        return msisauth


async def main():
    with open("AUTH_CREDENTIALS", "r") as f:
        username, password = (s.strip() for s in f.readlines())

    async with httpx.AsyncClient() as client:
        auther = LMSAuther(client)
        print("Getting MSISAuth token:\n")
        msis = await auther.get_msisauth_token(username, password)
        print(msis)
        print("\n=============================================\n")
        print("Getting Bearer token:")
        bearer = await auther.get_bearer_token(msis)
        print(bearer)


if __name__ == "__main__":
    asyncio.run(main())
