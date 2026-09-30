"""Stage 4 sample — the shipped smoke checks.

This is a sample, not the graded suite. It shows the shape of each surface once so a
service can be wired up against it; the spec is the contract and the graded checks are
the spec's. Passing everything here means the wiring is right, not that the stage holds.
"""
from types import SimpleNamespace

import pytest

import fixtures as fx
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(4)


@pytest.fixture
def world(reset, api):
    seeded = fx.fixture()
    seeded["settlement_operator_ids"] = ["u_ada"]
    reset(seeded)
    return SimpleNamespace(
        ada=api().authenticate(fx.ADA["email"], fx.ADA["password"]),
        bob=api().authenticate(fx.BOB["email"], fx.BOB["password"]))


def pay(client, to_handle="bob", amount=1000):
    return assert_status(client.post("/payments", json={"to_handle": to_handle, "amount": amount},
                                     idempotency_key=new_key()), 201).json()


def refund(client, payment, amount=200, key=None):
    return client.post("/payments/" + payment["payment_id"] + "/refunds",
                       json={"amount": amount}, idempotency_key=key or new_key())


def batch(payment, amount=50):
    return {"corrections": [dict(payment_id=payment["payment_id"], expected_revision=1,
                                 amount=amount, effective_at=payment["created_at"],
                                 reason="correction")]}


def test_other_payments_carry_refund_of_null(world):
    assert pay(world.ada)["refund_of"] is None


def test_a_refund_is_a_linked_reverse_payment(world):
    payment = pay(world.ada)
    refunded = assert_status(refund(world.bob, payment), 201).json()
    assert refunded["refund_of"] == payment["payment_id"]
    assert (refunded["from_handle"], refunded["to_handle"], refunded["amount"]) == ("bob", "ada", 200)
    assert assert_status(world.ada.get("/me"), 200).json()["total"] == fx.ADA["balance"] - 800


def test_a_refund_replay_returns_the_original_body(world):
    payment, key = pay(world.ada), new_key()
    first = assert_status(refund(world.bob, payment, key=key), 201).json()
    assert assert_status(refund(world.bob, payment, key=key), 200).json() == first


def test_operator_can_correct_a_payment_in_a_batch(world):
    payment = pay(world.ada, amount=100)
    body = assert_status(world.ada.post("/correction-batches", json=batch(payment),
                                        idempotency_key=new_key()), 201).json()
    assert body["correction_batch_id"] and body["recorded_at"]
    assert len(body["revisions"]) == 1
    assert world.ada.get("/me").json()["balance"] == fx.ADA["balance"] - 50


def test_a_batch_needs_a_settlement_operator(world):
    payment = pay(world.bob, to_handle="ada", amount=100)
    assert_error(world.bob.post("/correction-batches", json=batch(payment),
                                idempotency_key=new_key()), 403, "forbidden")
