import re
from collections.abc import Mapping, Sequence

MAX_MEMBERS = 12
MAX_CENTS = 99_999_999_999
CATEGORIES = (
    "Food & drink",
    "Groceries",
    "Transport",
    "Lodging",
    "Activities",
    "Other",
)


def cents(text: str) -> int:
    if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", text.strip()):
        raise ValueError("Enter a dollar amount with up to two decimal places.")
    dollars, _, fraction = text.strip().partition(".")
    return int(dollars) * 100 + int(fraction.ljust(2, "0"))


def money(amount: int) -> str:
    dollars, fraction = divmod(abs(amount), 100)
    return f"{'-' if amount < 0 else ''}${dollars:,}.{fraction:02d}"


def valid_amount(amount: int):
    if type(amount) is not int or not 0 < amount <= MAX_CENTS:
        raise ValueError("Enter an amount greater than zero and below $1 billion.")


def shares_for(members: Sequence[str], amount: int, shares: Mapping[str, int] | None):
    valid_amount(amount)
    if shares is None:
        each, extra = divmod(amount, len(members))
        return {m: each + (i < extra) for i, m in enumerate(members)}
    if set(shares) != set(members) or any(
        type(v) is not int or v < 0 for v in shares.values()
    ):
        raise ValueError("Enter a nonnegative share for each member.")
    if sum(shares.values()) != amount:
        raise ValueError(
            f"Shares total {money(sum(shares.values()))}. They must add up to {money(amount)}."
        )
    return dict(shares)


def balances(members, expenses, payments):
    net = dict.fromkeys(members, 0)
    for e in expenses:
        net[e["payer"]] += e["amount"]
        for member, share in e["shares"].items():
            net[member] -= share
    for p in payments:
        net[p["sender"]] += p["amount"]
        net[p["receiver"]] -= p["amount"]
    return net


def settlements(net: Mapping[str, int]) -> list[tuple[str, str, int]]:
    """Partition into as many zero-sum blocks as possible, then clear each block."""
    if sum(net.values()) != 0:
        raise ValueError("Balances must add up to zero.")
    people = [m for m, amount in net.items() if amount]
    if len(people) > MAX_MEMBERS:
        raise ValueError(f"Groups support up to {MAX_MEMBERS} members.")
    size = 1 << len(people)
    totals, blocks, last = [0] * size, [0] * size, [0] * size
    for mask in range(1, size):
        bit = mask & -mask
        totals[mask] = totals[mask ^ bit] + net[people[bit.bit_length() - 1]]
        remaining = mask
        while remaining:
            bit = remaining & -remaining
            if not last[mask] or blocks[mask ^ bit] > blocks[mask ^ last[mask]]:
                last[mask] = bit
            remaining ^= bit
        blocks[mask] = blocks[mask ^ last[mask]] + (totals[mask] == 0)

    transfers = []
    debtors, creditors = [], []
    mask = size - 1
    while mask:
        bit = last[mask]
        person = people[bit.bit_length() - 1]
        (debtors if net[person] < 0 else creditors).append([person, abs(net[person])])
        mask ^= bit
        if totals[mask] == 0:
            while debtors:
                debtor, creditor = debtors[-1], creditors[-1]
                amount = min(debtor[1], creditor[1])
                transfers.append((debtor[0], creditor[0], amount))
                debtor[1] -= amount
                creditor[1] -= amount
                if not debtor[1]:
                    debtors.pop()
                if not creditor[1]:
                    creditors.pop()
    return transfers
