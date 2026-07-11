"""Login page object. One class per screen; expose intent-level methods
(`login`, `error_is_visible`) rather than raw selectors to your tests."""
from playwright.sync_api import expect

from pages.base_page import BasePage


class LoginPage(BasePage):
    def login(self, username: str, password: str) -> None:
        self.page.fill("#username", username)
        self.page.fill("#password", password)
        self.page.click("#login-button")

    def expect_error_visible(self) -> None:
        expect(self.page.locator("#login-error")).to_be_visible()
