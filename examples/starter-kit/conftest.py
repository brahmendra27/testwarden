"""Fixtures for the starter kit.

By default this serves the bundled demo site so the kit runs offline out of the
box. To point the tests at YOUR app instead, set BASE_URL and the fixture skips
the bundled server:

    BASE_URL=https://staging.your-app.com pytest
"""
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pages.catalog_page import CatalogPage
from pages.login_page import LoginPage

SITE_DIR = Path(__file__).parent / "site"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def base_url():
    external = os.environ.get("BASE_URL")
    if external:
        yield external.rstrip("/")
        return
    handler = partial(_QuietHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def login_page(page, base_url):
    return LoginPage(page, base_url)


@pytest.fixture()
def catalog_page(page, base_url):
    return CatalogPage(page, base_url)


@pytest.fixture()
def logged_in(login_page, catalog_page):
    """Arrive on the catalog as a signed-in user — the common precondition."""
    login_page.open()
    login_page.login("standard_user", "secret")
    catalog_page.expect_loaded("standard_user")
    return catalog_page
