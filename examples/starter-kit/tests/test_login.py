"""Login tests. Note how the test body reads as intent — the selectors live in
the page objects, so a UI change means editing one page class, not every test."""
import pytest


@pytest.mark.smoke
def test_valid_login(login_page, catalog_page):
    login_page.open()
    login_page.login("standard_user", "secret")
    catalog_page.expect_loaded("standard_user")


@pytest.mark.regression
def test_invalid_login_shows_error(login_page):
    login_page.open()
    login_page.login("standard_user", "wrong-password")
    login_page.expect_error_visible()
