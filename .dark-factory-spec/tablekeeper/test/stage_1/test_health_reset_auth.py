"""Harness contract (§3) and authentication (§6)."""
import pytest

import fixtures as fx
from harness.http import assert_error, assert_status

pytestmark = pytest.mark.stage(1)


def test_reset_needs_no_authentication(reset):
    reset(fx.fixture())


def test_seeded_user_can_log_in_immediately(reset, api):
    reset(fx.fixture())
    assert_status(api().login(fx.ADA["email"], fx.ADA["password"]), 200)


@pytest.mark.parametrize("email,password,status,code", [
    (fx.ADA["email"], "correct horse", 409, "email_taken"),
    ("short@example.com", "1234567", 422, "validation_failed"),
    ("not-an-email", "correct horse", 422, "validation_failed"),
])
def test_signup_rejections(world, email, password, status, code):
    assert_error(world.ada.signup(email, password, "X"), status, code)


def test_signup_field_with_wrong_json_type_is_malformed(world):
    assert_error(world.ada.post("/auth/signup", json={
        "email": 17, "password": "correct horse", "display_name": "X"},
        token=None), 400, "malformed_request")


@pytest.mark.parametrize("email,password", [
    (fx.ADA["email"], "wrong password"),
    ("nobody@example.com", "correct horse"),
])
def test_login_failures_are_401(world, email, password):
    assert_error(world.ada.login(email, password), 401, "unauthenticated")


@pytest.mark.parametrize("path", ["/reservations", "/reservations/ABC123"])
def test_protected_endpoints_reject_missing_token(world, anon, path):
    assert_error(anon.get(path), 401, "unauthenticated")


def test_protected_endpoints_reject_unknown_token(api):
    assert_error(api("not-a-real-token").get("/reservations"), 401, "unauthenticated")


def test_restaurant_detail_is_public(world, anon):
    assert_status(anon.get(f"/restaurants/{world.rid}"), 200)
