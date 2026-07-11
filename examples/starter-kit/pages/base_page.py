"""Base page: shared helpers every page object inherits.

Keep cross-cutting concerns (navigation, waiting, common locators) here so your
individual page objects stay focused on one screen.
"""
from playwright.sync_api import Page


class BasePage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url

    def open(self, path: str = "/") -> None:
        self.page.goto(self.base_url.rstrip("/") + path)

    @property
    def title_text(self) -> str:
        return self.page.locator("#page-title").inner_text()
