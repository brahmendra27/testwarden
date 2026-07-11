"""Catalog page object — the screen shown after a successful login."""
from playwright.sync_api import expect

from pages.base_page import BasePage


class CatalogPage(BasePage):
    def expect_loaded(self, username: str) -> None:
        expect(self.page.locator("#catalog-view")).to_be_visible()
        expect(self.page.locator("#current-user")).to_have_text(username)

    def search(self, term: str) -> None:
        self.page.fill("#search", term)

    def visible_products(self) -> list[str]:
        items = self.page.locator("#product-list li:visible")
        return [items.nth(i).inner_text() for i in range(items.count())]

    def add_first_to_cart(self) -> None:
        self.page.click("#add-first")

    def expect_cart_count(self, count: int) -> None:
        expect(self.page.locator("#cart-count")).to_have_text(str(count))
