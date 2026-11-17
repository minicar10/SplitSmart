import os
from collections import Counter
from datetime import date
from pathlib import Path

import streamlit as st

from splitsmart import views
from splitsmart.money import CATEGORIES, balances, cents, money, settlements
from splitsmart.store import Ledger

ROOT = Path(__file__).resolve().parent
st.set_page_config(
    page_title="SplitSmart · Group ledger", page_icon="🧾", layout="wide"
)
st.html(f"<style>{(ROOT / 'splitsmart/style.css').read_text()}</style>")


@st.cache_resource
def get_ledger(path):
    return Ledger(path)


db = get_ledger(os.environ.get("SPLITSMART_DB", str(ROOT / "data/splitsmart.sqlite3")))


def dismiss():
    st.session_state.pop("dialog", None)
    st.session_state.pop("editing", None)


def done(message):
    dismiss()
    st.session_state["notice"] = message
    st.rerun()


def dollars(amount):
    return f"{amount // 100}.{amount % 100:02d}"


@st.dialog("Create a group", on_dismiss=dismiss)
def new_group():
    with st.form("new-group"):
        name = st.text_input(
            "Group name", placeholder="e.g. Apartment 4B", max_chars=80
        )
        members = st.text_area(
            "Members",
            placeholder="Alice\nBob\nCharlie",
            help="One name per line. Extra cents go to members in this order.",
        )
        if st.form_submit_button("Create group", type="primary"):
            try:
                gid = db.create_group(
                    name, [m for m in members.splitlines() if m.strip()]
                )
            except ValueError as err:
                st.error(str(err))
            else:
                st.session_state["next_group"] = gid
                done("Group created.")


@st.dialog("Add expense", on_dismiss=dismiss)
def add_expense(gid, members):
    expense_fields(gid, members, None)


@st.dialog("Edit expense", on_dismiss=dismiss)
def edit_expense(gid, members, expenses):
    by_id = {e["expense_id"]: e for e in expenses}
    eid = st.selectbox(
        "Expense",
        by_id.keys(),
        format_func=lambda i: (
            f"{by_id[i]['title']} · {views.display_day(by_id[i]['day'])} · {money(by_id[i]['amount'])} (#{i})"
        ),
    )
    expense_fields(gid, members, by_id[eid])


def expense_fields(gid, members, e):
    e = e or {}
    key = f"expense-{gid}-{e.get('expense_id', 'new')}-{e.get('version', 0)}"
    mode = st.radio(
        "Split method",
        ["Equal", "Custom"],
        index=int(e.get("mode") == "Custom"),
        horizontal=True,
        key=key + "-mode",
    )
    with st.form(key):
        title = st.text_input(
            "Description",
            value=e.get("title", ""),
            max_chars=100,
            placeholder="e.g. Dinner at Pine House",
        )
        a, b = st.columns(2)
        amount = a.text_input(
            "Amount ($)", value=dollars(e["amount"]) if e else "", placeholder="0.00"
        )
        payer = b.selectbox(
            "Paid by", members, index=members.index(e["payer"]) if e else 0
        )
        a, b = st.columns(2)
        category = a.selectbox(
            "Category", CATEGORIES, index=CATEGORIES.index(e["category"]) if e else 0
        )
        day = b.date_input(
            "Expense date", value=date.fromisoformat(e["day"]) if e else date.today()
        )
        raw = {}
        if mode == "Custom":
            for m in members:
                raw[m] = st.text_input(
                    f"{m}’s share ($)",
                    value=dollars(e["shares"][m]) if e else "0.00",
                    key=f"{key}-share-{m}",
                )
        else:
            st.caption(
                "Split across all members. Extra cents follow the saved member order."
            )
        if st.form_submit_button(
            "Save changes" if e else "Save expense", type="primary"
        ):
            try:
                db.save_expense(
                    gid,
                    title,
                    cents(amount),
                    payer,
                    {m: cents(v) for m, v in raw.items()} if mode == "Custom" else None,
                    category,
                    day.isoformat(),
                    expense_id=e.get("expense_id"),
                    version=e.get("version"),
                )
            except ValueError as err:
                st.error(str(err))
            else:
                done("Expense updated." if e else "Expense added.")
    if e:
        with st.expander("Delete this expense"):
            st.write(
                "Deleting removes this expense from balances. Its revisions and any recorded payments stay in the ledger."
            )
            if st.button("Confirm deletion", key=key + "-delete"):
                try:
                    db.delete_expense(gid, e["expense_id"], e["version"])
                except ValueError as err:
                    st.error(str(err))
                else:
                    done("Expense deleted.")


@st.dialog("Settle up", on_dismiss=dismiss)
def settle(plan):
    if not plan:
        st.success("Everyone is settled up.")
        return
    count = len(plan)
    st.write(f"This group can settle in {count} payment{'s' if count != 1 else ''}.")
    st.html(
        views.listing(
            [
                views.row(
                    views.icon("↗", "#e2eddb"),
                    f"{a} pays {b}",
                    "Suggested payment",
                    money(v),
                )
                for a, b, v in plan
            ],
            "",
        )
    )
    st.caption("Once money changes hands, use Record payment to update the ledger.")


@st.dialog("Record payment", on_dismiss=dismiss)
def record_payment(gid, members, plan):
    sender, receiver, amount = plan[0] if plan else (*members[:2], 0)
    with st.form("record-payment"):
        a, b = st.columns(2)
        sender = a.selectbox("From", members, index=members.index(sender))
        receiver = b.selectbox("To", members, index=members.index(receiver))
        raw = st.text_input(
            "Amount ($)", value=dollars(amount) if amount else "", placeholder="0.00"
        )
        day = st.date_input("Payment date", value=date.today())
        if st.form_submit_button("Save payment", type="primary"):
            try:
                db.pay(gid, sender, receiver, cents(raw), day.isoformat())
            except ValueError as err:
                st.error(str(err))
            else:
                done("Payment recorded.")


groups = db.groups()
name_counts = Counter(groups.values())
group_labels = {
    gid: name if name_counts[name] == 1 else f"{name} (#{gid})"
    for gid, name in groups.items()
}
if "next_group" in st.session_state:
    st.session_state["active_group"] = st.session_state.pop("next_group")
with st.container(horizontal=True, vertical_alignment="center"):
    with st.container(width="stretch"):
        st.html(
            '<div class="brand"><span class="brand-mark" aria-hidden="true"><i></i><b></b></span>SplitSmart</div>'
        )
    gid = st.selectbox(
        "Current group",
        groups.keys(),
        format_func=group_labels.get,
        key="active_group",
        label_visibility="collapsed",
        width=190,
    )
    if st.button("New group", icon=":material/group_add:"):
        st.session_state["dialog"] = "group"

group, expenses, payments, history = db.snapshot(gid)
members = group["members"]
net = balances(members, expenses, payments)
plan = settlements(net)
st.html('<div class="top-rule"></div>')
st.html(views.hero(group, expenses))
st.html(
    views.summary(
        sum(e["amount"] for e in expenses), sum(v for v in net.values() if v > 0), plan
    )
)
if notice := st.session_state.pop("notice", None):
    st.toast(notice, icon="✅")

left, right = st.columns([1.65, 1], gap="large")
with left:
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.html('<h2 class="section-head">Group activity</h2>')
        if st.button("Add expense", icon=":material/add:", type="primary"):
            st.session_state["dialog"] = "add"
    expenses_tab, payments_tab, history_tab = st.tabs(
        ["Expenses", "Payments", "Edit history"]
    )
    with expenses_tab:
        st.html(views.expense_list(expenses))
        if expenses and st.button("Edit expense", icon=":material/edit:"):
            st.session_state["dialog"] = "edit"
            st.session_state["editing"] = expenses
    with payments_tab:
        st.html(
            views.listing(
                [
                    views.row(
                        views.icon("↗", "#dcebdc"),
                        f"{p['sender']} paid {p['receiver']}",
                        views.display_day(p["day"]),
                        money(p["amount"]),
                    )
                    for p in payments
                ],
                "Recorded payments will appear here.",
            )
        )
    with history_tab:
        if not history:
            st.caption("Saved versions will appear after you add an expense.")
        for r in history:
            action = (
                "Deleted"
                if r["deleted"]
                else "Added"
                if r["version"] == 1
                else "Edited"
            )
            with st.expander(f"{action} · {r['title']} · v{r['version']}"):
                st.text(
                    f"Expense #{r['expense_id']} · Saved {r['saved']} UTC\n{money(r['amount'])} paid by {r['payer']} · {r['category']}\n{views.display_day(r['day'])} · {r['mode']} split"
                )
                st.text("\n".join(f"{m}  {money(s)}" for m, s in r["shares"].items()))
with right:
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.html('<h2 class="section-head">Member balances</h2>')
        if st.button("Settle up", icon=":material/compare_arrows:"):
            st.session_state["dialog"] = "settle"
    st.html(views.balance_list(net))
    if st.button("Record payment", icon=":material/payments:"):
        st.session_state["dialog"] = "pay"

match st.session_state.get("dialog"):
    case "group":
        new_group()
    case "add":
        add_expense(gid, members)
    case "edit":
        edit_expense(gid, members, st.session_state["editing"])
    case "settle":
        settle(plan)
    case "pay":
        record_payment(gid, members, plan)
