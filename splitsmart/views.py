from datetime import date
from html import escape

from splitsmart.money import CATEGORIES, money

COLORS = [
    ("#d7e6c9", "#3d5941"),
    ("#ffe2b9", "#805833"),
    ("#deddf0", "#57517a"),
    ("#f4cbba", "#784c40"),
]
ICONS = dict(
    zip(
        CATEGORIES,
        [
            ("☕", "#fde8d8"),
            ("🛒", "#e0edd6"),
            ("🚙", "#dce9ec"),
            ("⌂", "#e8e3f4"),
            ("★", "#f8e9be"),
            ("▤", "#e4e9df"),
        ],
    )
)


def avatar(member, index):
    bg, fg = COLORS[index % len(COLORS)]
    initials = "".join(s[0] for s in member.split()[:2]).upper()
    return f'<span class="avatar" style="background:{bg};color:{fg}">{escape(initials)}</span>'


def hero(group, expenses):
    members = group["members"]
    stack = "".join(avatar(m, i) for i, m in enumerate(members[:5]))
    total = sum(e["amount"] for e in expenses)
    return f"""<section class="hero"><div class="hero-text">
    <div class="kicker">{"DEMO GROUP" if group["demo"] else "GROUP LEDGER"}</div>
    <h1>{escape(group["name"])}</h1><div class="members"><span class="stack">{stack}</span>
    {len(members)} members</div></div><div class="art" aria-hidden="true">
    <div class="paper"><div class="paper-kicker">GROUP RECEIPT</div><div class="paper-amt">{money(total)}</div>
    <div class="paper-line"><span>EXPENSES</span><b>{len(expenses):02d}</b></div><div class="barcode"></div></div>
    <div class="stamp">½</div></div></section>"""


def summary(total, outstanding, plan):
    items = [
        ("Group spending", money(total)),
        ("Left to settle", money(outstanding)),
        ("Suggested payments", str(len(plan))),
    ]
    return (
        '<div class="summary">'
        + "".join(
            f'<div class="summary-item"><div class="label">{label}</div><div class="metric">{value}</div></div>'
            for label, value in items
        )
        + "</div>"
    )


def display_day(day):
    return date.fromisoformat(day).strftime("%b %d, %Y").replace(" 0", " ")


def row(icon, name, sub, amount, kind=""):
    return f'<div class="row">{icon}<div class="detail"><div class="name">{escape(name)}</div><div class="sub">{escape(sub)}</div></div><div class="val {kind}">{escape(amount)}</div></div>'


def icon(symbol, color):
    return f'<div class="cat" style="background:{color}" aria-hidden="true"><span>{symbol}</span></div>'


def listing(rows, empty):
    return (
        '<div class="ledger-list">' + "".join(rows) + "</div>"
        if rows
        else f'<div class="empty">{empty}</div>'
    )


def expense_list(expenses):
    return listing(
        [
            row(
                icon(*ICONS[e["category"]]),
                e["title"],
                f"{e['payer']} paid · {display_day(e['day'])}",
                money(e["amount"]),
            )
            for e in expenses
        ],
        "Add the first expense to start this group’s ledger.",
    )


def balance_list(net):
    return listing(
        [
            row(
                avatar(m, i),
                m,
                "Gets back" if v > 0 else "Owes" if v < 0 else "Settled",
                money(abs(v)),
                "owe" if v < 0 else "credit" if v > 0 else "",
            )
            for i, (m, v) in enumerate(net.items())
        ],
        "",
    )
