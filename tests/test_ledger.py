from functools import cache
from itertools import product

import pytest

from splitsmart.money import balances, cents, money, settlements
from splitsmart.store import Ledger

DAY = "2026-03-18"


@pytest.fixture
def db(tmp_path):
    return Ledger(tmp_path / "ledger.sqlite")


def save(db, gid, payer, amount, shares=None, **kwargs):
    return db.save_expense(
        gid, "Dinner", amount, payer, shares, "Food & drink", DAY, **kwargs
    )


def state(db, gid):
    group, expenses, payments, _ = db.snapshot(gid)
    result = balances(group["members"], expenses, payments)
    assert sum(result.values()) == 0
    return result


def test_saved_order_rounding(db):
    gid = db.create_group("Roommates", ["Alice", "Bob", "Charlie"])
    save(db, gid, "Alice", 1000)
    assert db.snapshot(gid)[1][0]["shares"] == {
        "Alice": 334,
        "Bob": 333,
        "Charlie": 333,
    }
    assert state(db, gid) == {"Alice": 666, "Bob": -333, "Charlie": -333}
    save(db, gid, "Charlie", 2)
    assert state(db, gid) == {"Alice": 665, "Bob": -334, "Charlie": -331}


def test_edits_deletion_and_payment_survive_restart(db):
    gid = db.create_group("Pair", ["Alice", "Bob"])
    eid = save(db, gid, "Alice", 2000)
    db.pay(gid, "Bob", "Alice", 1000, DAY)
    assert state(db, gid) == {"Alice": 0, "Bob": 0}
    save(db, gid, "Alice", 800, expense_id=eid, version=1)
    assert state(db, gid) == {"Alice": -600, "Bob": 600}
    with pytest.raises(ValueError, match="changed"):
        db.delete_expense(gid, eid, 1)
    db.delete_expense(gid, eid, 2)
    reopened = Ledger(db.path)
    _, expenses, payments, history = reopened.snapshot(gid)
    assert expenses == [] and [p["amount"] for p in payments] == [1000]
    assert [(r["amount"], r["deleted"]) for r in history] == [
        (800, 1),
        (800, 0),
        (2000, 0),
    ]
    assert state(reopened, gid) == {"Alice": -1000, "Bob": 1000}
    assert len(reopened.groups()) == 2


def test_invalid_split_rolls_back(db):
    gid = db.create_group("Trip", ["Alice", "Bob", "Charlie"])
    before = db.snapshot(gid)
    with pytest.raises(ValueError, match=r"Shares total \$14.00"):
        save(db, gid, "Alice", 1500, {"Alice": 500, "Bob": 400, "Charlie": 500})
    assert db.snapshot(gid) == before
    assert list(state(db, gid).values()) == [0, 0, 0]


def test_cycle(db):
    names = ["Alice", "Bob", "Charlie"]
    gid = db.create_group("Cycle", names)
    for i, payer in enumerate(names):
        debtor = names[i - 1]
        save(db, gid, payer, 1000, {m: 1000 if m == debtor else 0 for m in names})
    assert settlements(state(db, gid)) == []


def test_pair_match():
    net = {"Alice": 600, "Bob": 400, "Charlie": -400, "Dana": -600}
    assert set(settlements(net)) == {("Charlie", "Bob", 400), ("Dana", "Alice", 600)}


@cache
def brute_force(values):
    """Try every legal debtor/creditor pair and every positive whole-unit transfer."""
    if not any(values):
        return 0
    best = float("inf")
    for i, debt in enumerate(values):
        for j, credit in enumerate(values):
            for amount in range(1, min(-debt, credit) + 1):
                after = list(values)
                after[i] += amount
                after[j] -= amount
                best = min(best, 1 + brute_force(tuple(after)))
    return best


@pytest.mark.parametrize("size", [4, 5])
def test_optimal_against_exhaustive_transfers(size):
    for prefix in product(range(-2, 3), repeat=size - 1):
        values = (*prefix, -sum(prefix))
        net = dict(enumerate(values))
        plan = settlements(net)
        assert len(plan) == brute_force(values)
        for sender, receiver, amount in plan:
            assert 0 < amount <= min(-net[sender], net[receiver])
            net[sender] += amount
            net[receiver] -= amount
        assert not any(net.values())


@pytest.mark.parametrize("text", ["1.001", "1e2", "-0.20", "NaN", "", "1000000000"])
def test_malformed_money(text):
    with pytest.raises(ValueError):
        cents(text)


def test_money_precision():
    assert cents("100000000.01") == 10_000_000_001
    assert money(-333) == "-$3.33"


def test_group_isolation_and_payment_validation(db):
    a = db.create_group("One", ["Alice", "Bob"])
    b = db.create_group("Two", ["Alice", "Bob"])
    eid = save(db, a, "Bob", 200)
    with pytest.raises(ValueError):
        save(db, b, "Alice", 500, expense_id=eid, version=1)
    with pytest.raises(ValueError):
        db.pay(a, "Bob", "Bob", 100, DAY)
    with pytest.raises(ValueError):
        db.pay(a, "Bob", "Charlie", 100, DAY)
    assert list(state(db, b).values()) == [0, 0]
    assert state(db, a) == {"Alice": -100, "Bob": 100}
