# SplitSmart

SplitSmart is a local group expense ledger built with Python, Streamlit, and SQLite. Create a group, enter shared expenses, and see the fewest payments needed to settle everyone's balances.

## Run locally

With uv and Python 3.11 or newer, run this command from the checkout.

```sh
uv run --frozen streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit. The first launch creates **Cabin weekend**, a labeled demo group with four members and five expenses. Choose **New group** for a blank ledger. Each group supports 2–12 members and uses US dollars.

SQLite stores the ledger in `data/splitsmart.sqlite3` across restarts. Set `SPLITSMART_DB` to choose another file. Anyone with access to a running instance can view and edit its groups.

## Try the edit-after-payment demo

1. Create a group with Alice and Bob. Add a $20 dinner paid by Alice and split it equally. Bob owes Alice $10.
2. Open **Settle up** to see the suggested transfer. Use **Record payment** to enter Bob's $10 payment to Alice. Both balances reach zero.
3. Under **Expenses**, choose **Edit expense** and change dinner to $8. Alice now owes Bob $6.
4. Delete the dinner from its edit dialog. Alice now owes Bob $10. **Payments** retains his original transfer, and **Edit history** shows all three versions of dinner.

## Calculation rules

- The ledger stores integer cents. Equal splits distribute leftover cents in saved member order. Custom splits can include zero shares and must sum to the expense total.
- Each expense revision preserves its payer, amount, date, category, and shares. Balances use the latest active revision plus all recorded payments. A version check prevents an older edit form from overwriting a newer change.
- The settlement planner uses subset dynamic programming to maximize the number of disjoint zero-balance groups. A connected group of `k` nonzero balances needs at least `k − 1` transfers. Clearing each block in a maximum partition attains that bound. Planning takes `O(n × 2ⁿ)` time and `O(2ⁿ)` space.

## Verification and implementation

```sh
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

The MVP passes 17 tests. They cover the four scenarios in the project brief, persistence after reopening SQLite, stale edits, group isolation, and Streamlit form submissions. An independent brute-force solver tries every debtor, creditor, and whole-unit transfer on 750 four- and five-person balance vectors. Each suggested plan must clear every balance and match the brute-force minimum.

Codex implemented the interface, SQLite ledger, calculations, and tests from the team's project brief. Runtime dependencies are declared in `pyproject.toml`, with resolved versions in `uv.lock`. SQLite comes with Python. The development tools are pytest and Ruff.
