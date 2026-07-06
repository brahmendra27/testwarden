"""Demo suite for the bundled static shop site.

Includes one deliberately flaky test and one hard failure so the dashboard
has something interesting to show.
"""
import random

from playwright.sync_api import Page, expect


def test_home_title(page: Page, site_url: str):
    page.goto(site_url)
    expect(page).to_have_title("TestWarden Demo Shop")
    expect(page.locator("#page-title")).to_have_text("TestWarden Demo Shop")


def test_nav_links_visible(page: Page, site_url: str):
    page.goto(site_url)
    for link_id in ("#nav-home", "#nav-products", "#nav-about"):
        expect(page.locator(link_id)).to_be_visible()


def test_login_success(page: Page, site_url: str):
    page.goto(site_url)
    page.fill("#username", "demo")
    page.fill("#password", "demo123")
    page.click("#login-button")
    expect(page.locator("#welcome")).to_have_text("Welcome back, demo!")


def test_login_wrong_password(page: Page, site_url: str):
    page.goto(site_url)
    page.fill("#username", "demo")
    page.fill("#password", "nope")
    page.click("#login-button")
    expect(page.locator("#login-error")).to_be_visible()
    expect(page.locator("#welcome")).to_be_hidden()


def test_cart_counter_increments(page: Page, site_url: str):
    page.goto(site_url)
    for _ in range(3):
        page.click("#add-item")
    expect(page.locator("#counter")).to_have_text("3")


def test_product_filter(page: Page, site_url: str):
    page.goto(site_url)
    page.fill("#search", "rocket")
    expect(page.locator("#products-list li", has_text="Rocket skates")).to_be_visible()
    expect(page.locator("#products-list li", has_text="Anvil")).to_be_hidden()


def test_delayed_promo_banner_appears(page: Page, site_url: str):
    page.goto(site_url)
    # Banner is injected after ~600ms; Playwright auto-waits for it.
    expect(page.locator("#promo-banner")).to_be_visible(timeout=3000)


def test_footer_present(page: Page, site_url: str):
    page.goto(site_url)
    expect(page.locator("#footer")).to_contain_text("Demo Shop")


def test_flaky_promo_click(page: Page, site_url: str):
    """Deliberately flaky: ~40% of attempts look for an element that never
    existed. With --reruns 2 it usually passes on retry -> shows up amber."""
    page.goto(site_url)
    if random.random() < 0.4:
        expect(page.locator("#flash-sale-banner")).to_be_visible(timeout=1500)
    else:
        expect(page.locator("#promo-banner")).to_be_visible(timeout=3000)


def test_checkout_button(page: Page, site_url: str):
    """Deliberately broken: the checkout button was never implemented.
    Produces a hard failure with screenshot + trace on every run."""
    page.goto(site_url)
    page.click("#add-item")
    expect(page.locator("#checkout-button")).to_be_visible(timeout=2000)
