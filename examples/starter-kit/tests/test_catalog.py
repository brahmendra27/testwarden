"""Catalog tests, all starting from the `logged_in` precondition fixture."""
import pytest


@pytest.mark.smoke
def test_catalog_lists_products(logged_in):
    assert "Widget" in logged_in.visible_products()


@pytest.mark.regression
def test_search_filters_products(logged_in):
    logged_in.search("gad")
    products = logged_in.visible_products()
    assert products == ["Gadget"]


@pytest.mark.regression
def test_add_to_cart_updates_count(logged_in):
    logged_in.add_first_to_cart()
    logged_in.expect_cart_count(1)


# Example: a test you suspect is flaky can be quarantined. FlakeLens' reporter
# turns this into a non-strict xfail (CI stays green) while still tracking its
# real outcome so the SelfHeal agent can fix and release it later.
#
# @pytest.mark.quarantine
# @pytest.mark.regression
# def test_something_flaky(logged_in):
#     ...
