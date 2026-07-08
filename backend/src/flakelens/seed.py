"""Seed demo data: one project, ~60 test cases, 30 daily runs with realistic
flaky/regression patterns. Drives the real ingestion + finalization pipeline.

Usage: python -m flakelens.seed
"""
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from flakelens.auth import create_api_key
from flakelens.db import Base, SessionLocal, engine
from flakelens.models import Project
from flakelens.schemas.ingest import AttemptIn, ResultEnvelope, RunCreate
from flakelens.services.ingestion import get_or_create_run, ingest_results
from flakelens.services.stats import finalize_run

FILES = {
    "tests/test_login.py": ["test_valid_login", "test_invalid_password", "test_locked_account",
                            "test_remember_me", "test_logout", "test_password_reset",
                            "test_sso_redirect", "test_session_expiry", "test_mfa_prompt",
                            "test_login_rate_limit"],
    "tests/test_checkout.py": ["test_guest_checkout", "test_saved_card", "test_apply_coupon",
                               "test_invalid_coupon", "test_shipping_options", "test_tax_calculation",
                               "test_order_summary", "test_payment_declined", "test_address_validation",
                               "test_order_confirmation"],
    "tests/test_search.py": ["test_basic_search", "test_no_results", "test_search_filters",
                             "test_search_pagination", "test_search_sorting", "test_autocomplete",
                             "test_special_characters", "test_category_search", "test_recent_searches",
                             "test_search_analytics"],
    "tests/test_profile.py": ["test_view_profile", "test_edit_profile", "test_avatar_upload",
                              "test_change_email", "test_change_password", "test_notification_prefs",
                              "test_delete_account", "test_privacy_settings", "test_linked_accounts",
                              "test_activity_log"],
    "tests/test_cart.py": ["test_add_to_cart", "test_remove_from_cart", "test_update_quantity",
                           "test_cart_persistence", "test_cart_merge_on_login", "test_empty_cart",
                           "test_cart_totals", "test_save_for_later", "test_stock_warning",
                           "test_cart_expiry"],
    "tests/test_navigation.py": ["test_home_page", "test_main_menu", "test_footer_links",
                                 "test_breadcrumbs", "test_mobile_menu", "test_mega_menu",
                                 "test_back_button", "test_deep_links", "test_404_page",
                                 "test_sitemap"],
}

INTRA_FLAKY = "tests/test_checkout.py::test_apply_coupon[chromium]"
FLIP_FLAKY = "tests/test_search.py::test_search_pagination[chromium]"
REGRESSION = "tests/test_login.py::test_remember_me[chromium]"
CART_INCIDENT_RUN = 15  # run index where several cart tests fail together

STACK_TEMPLATE = """    def {name}(page: Page):
        page.goto(BASE_URL + "{path}")
>       expect(locator).to_be_visible(timeout=5000)
E       {error_type}: {message}

{file}:42: {error_type}"""


def _failed_attempt(index: int, name: str, file: str, error_type: str, message: str,
                    duration: int) -> AttemptIn:
    return AttemptIn(
        index=index,
        status="failed",
        duration_ms=duration,
        error_type=error_type,
        error_message=message,
        stack_trace=STACK_TEMPLATE.format(
            name=name, path="/" + name.replace("test_", "").replace("_", "-"),
            error_type=error_type, message=message, file=file,
        ),
        stdout=f"navigating...\nwaiting for selector\n",
    )


def _envelope_for(file: str, name: str, run_index: int, rng: random.Random) -> ResultEnvelope:
    node_id = f"{file}::{name}[chromium]"
    base_duration = 500 + (hash(node_id) % 4500)
    duration = int(base_duration * rng.uniform(0.8, 1.2))
    status = "passed"
    attempts: list[AttemptIn] = []

    if node_id == INTRA_FLAKY and rng.random() < 0.5:
        # Fails on first attempt, passes on retry -> intra-run flaky.
        attempts = [
            _failed_attempt(0, name, file, "TimeoutError",
                            "Timed out 5000ms waiting for locator('.coupon-applied')", 8000 + rng.randint(0, 500)),
            AttemptIn(index=1, status="passed", duration_ms=duration),
        ]
    elif node_id == FLIP_FLAKY and rng.random() < 0.3:
        # Fails outright some runs -> cross-run flip-flopping.
        status = "failed"
        message = "Locator('.pagination >> nth=2') resolved to hidden element"
        attempts = [_failed_attempt(i, name, file, "AssertionError", message,
                                    duration + rng.randint(0, 800)) for i in range(3)]
    elif node_id == REGRESSION and run_index > 20:
        status = "failed"
        message = "Expected checkbox 'Remember me' to be checked, but it was not"
        attempts = [_failed_attempt(i, name, file, "AssertionError", message, duration)
                    for i in range(3)]
    elif run_index == CART_INCIDENT_RUN and file == "tests/test_cart.py" and name in (
        "test_add_to_cart", "test_update_quantity", "test_cart_totals", "test_stock_warning"
    ):
        status = "failed"
        message = "TimeoutError: page.goto: net::ERR_CONNECTION_REFUSED at http://cart-service:8080"
        attempts = [_failed_attempt(i, name, file, "TimeoutError", message, 10_000)
                    for i in range(3)]
    elif name == "test_search_analytics" and run_index % 4 == 0:
        status = "skipped"
    elif rng.random() < 0.004:
        status = "failed"
        message = "Element <button data-testid='submit'> is not attached to the DOM"
        attempts = [_failed_attempt(0, name, file, "StaleElementError", message, duration)]

    if not attempts:
        attempts = [AttemptIn(index=0, status=status, duration_ms=duration)]
    final_duration = attempts[-1].duration_ms

    return ResultEnvelope(
        result_ref=str(uuid.uuid4()),
        framework="pytest-playwright",
        normalized_id=node_id,
        file_path=file,
        title=f"{name}[chromium]",
        status=status,
        duration_ms=final_duration,
        attempts=attempts,
        extras={"browser": "chromium", "seeded": True},
    )


def main() -> None:
    Base.metadata.create_all(engine)
    rng = random.Random(42)
    with SessionLocal() as db:
        if db.scalar(select(Project).where(Project.slug == "demo-web")) is not None:
            print("Project 'demo-web' already seeded - delete data/flakelens.db to reseed.")
            return
        project = Project(slug="demo-web", name="Demo Web App",
                          repo_url="https://github.com/example/demo-web")
        db.add(project)
        db.flush()
        api_key = create_api_key(db, project, name="demo key")

        now = datetime.now(timezone.utc)
        for run_index in range(1, 31):
            started = now - timedelta(days=30 - run_index, minutes=rng.randint(0, 120))
            branch = "feature/checkout-v2" if run_index % 5 == 0 else "main"
            run, _ = get_or_create_run(db, project.id, RunCreate(
                run_uuid=str(uuid.uuid4()),
                framework="pytest-playwright",
                started_at=started,
                branch=branch,
                commit_sha="%040x" % rng.getrandbits(160),
                environment="ci",
            ))
            envelopes = [
                _envelope_for(file, name, run_index, rng)
                for file, names in FILES.items()
                for name in names
            ]
            ingest_results(db, project.id, run, envelopes)
            total_ms = sum(e.duration_ms for e in envelopes)
            finalize_run(db, run, finished_at=started + timedelta(milliseconds=total_ms // 4))
        db.commit()

    key_file = Path("data")
    key_file.mkdir(parents=True, exist_ok=True)
    (key_file / "demo_api_key.txt").write_text(api_key)
    print("Seeded project 'demo-web' with 30 runs / 60 test cases.")
    print(f"Ingestion API key (also in data/demo_api_key.txt):\n  {api_key}")


if __name__ == "__main__":
    main()
