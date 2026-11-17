import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, timedelta
from pathlib import Path

from splitsmart.money import CATEGORIES, MAX_MEMBERS, shares_for, valid_amount

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, members TEXT NOT NULL, demo INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES groups
);
CREATE TABLE IF NOT EXISTS revisions (
 expense_id INTEGER NOT NULL REFERENCES expenses, version INTEGER NOT NULL,
 title TEXT NOT NULL, amount INTEGER NOT NULL, payer TEXT NOT NULL, shares TEXT NOT NULL,
 mode TEXT NOT NULL, category TEXT NOT NULL, day TEXT NOT NULL, deleted INTEGER NOT NULL,
 saved TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(expense_id, version)
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES groups,
 sender TEXT NOT NULL, receiver TEXT NOT NULL, amount INTEGER NOT NULL, day TEXT NOT NULL
);
"""


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            db.executescript(SCHEMA)
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM groups LIMIT 1").fetchone():
                members = ["Alex Morgan", "Jamie Chen", "Sam Rivera", "Taylor Reed"]
                group = self.insert_group(db, "Cabin weekend", members, True)
                examples = [
                    ("Lakeside cabin", 36000, 0, 3, 3),
                    ("Weekend groceries", 8640, 1, 1, 2),
                    ("Gas for the drive", 4800, 2, 2, 2),
                    ("Dinner at Pine House", 12800, 0, 0, 1),
                    ("Trailhead coffees", 2400, 3, 0, 0),
                ]
                for title, amount, who, category, days in examples:
                    self.write_expense(
                        db,
                        group,
                        members,
                        title,
                        amount,
                        members[who],
                        None,
                        CATEGORIES[category],
                        (date.today() - timedelta(days=days)).isoformat(),
                    )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def transaction(self, write=True):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db

    def insert_group(self, db, name, members, demo=False):
        return db.execute(
            "INSERT INTO groups(name,members,demo) VALUES (?,?,?)",
            (name, json.dumps(members), demo),
        ).lastrowid

    def create_group(self, name, members):
        name = name.strip()
        members = [m.strip() for m in members]
        if not name or len(name) > 80:
            raise ValueError("Give the group a name of 1–80 characters.")
        if not 2 <= len(members) <= MAX_MEMBERS:
            raise ValueError(f"Add between 2 and {MAX_MEMBERS} members.")
        if any(not m or len(m) > 60 for m in members) or len(
            {m.casefold() for m in members}
        ) != len(members):
            raise ValueError("Use distinct member names, each 1–60 characters long.")
        with self.transaction() as db:
            return self.insert_group(db, name, members)

    def groups(self):
        with self.transaction(False) as db:
            return {
                r["id"]: r["name"]
                for r in db.execute("SELECT id,name FROM groups ORDER BY id")
            }

    def group(self, db, gid):
        row = db.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()
        if not row:
            raise ValueError("Group no longer exists.")
        return {**row, "members": json.loads(row["members"])}

    def snapshot(self, gid):
        with self.transaction(False) as db:
            group = self.group(db, gid)
            rows = db.execute(
                """SELECT r.* FROM revisions r JOIN expenses e ON e.id=r.expense_id
                WHERE e.group_id=? ORDER BY r.day DESC, e.id DESC, r.version DESC""",
                (gid,),
            )
            history = [{**r, "shares": json.loads(r["shares"])} for r in rows]
            latest = {}
            for r in sorted(history, key=lambda r: r["version"]):
                latest[r["expense_id"]] = r
            expenses = [
                r for r in history if r is latest[r["expense_id"]] and not r["deleted"]
            ]
            payments = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM payments WHERE group_id=? ORDER BY day DESC,id DESC",
                    (gid,),
                )
            ]
            return (
                group,
                expenses,
                payments,
                sorted(
                    history,
                    key=lambda r: (r["saved"], r["expense_id"], r["version"]),
                    reverse=True,
                ),
            )

    def save_expense(
        self,
        gid,
        title,
        amount,
        payer,
        shares,
        category,
        day,
        *,
        expense_id=None,
        version=None,
    ):
        with self.transaction() as db:
            members = self.group(db, gid)["members"]
            return self.write_expense(
                db,
                gid,
                members,
                title,
                amount,
                payer,
                shares,
                category,
                day,
                expense_id,
                version,
            )

    def current_revision(self, db, gid, eid, version):
        row = db.execute(
            """SELECT r.* FROM revisions r JOIN expenses e ON e.id=r.expense_id
            WHERE e.group_id=? AND e.id=? ORDER BY version DESC LIMIT 1""",
            (gid, eid),
        ).fetchone()
        if not row or row["deleted"] or row["version"] != version:
            raise ValueError(
                "This expense changed. Close the form and reopen the latest version."
            )
        return row

    def write_expense(
        self,
        db,
        gid,
        members,
        title,
        amount,
        payer,
        shares,
        category,
        day,
        eid=None,
        version=None,
    ):
        title = title.strip()
        if not title or len(title) > 100:
            raise ValueError("Give the expense a description of 1–100 characters.")
        if payer not in members or category not in CATEGORIES:
            raise ValueError("Select a group member and a valid category.")
        day = date.fromisoformat(day).isoformat()
        split = shares_for(members, amount, shares)
        if eid is None:
            eid = db.execute(
                "INSERT INTO expenses(group_id) VALUES (?)", (gid,)
            ).lastrowid
            version = 0
        else:
            self.current_revision(db, gid, eid, version)
        db.execute(
            """INSERT INTO revisions(expense_id,version,title,amount,payer,shares,mode,category,day,deleted)
                       VALUES (?,?,?,?,?,?,?,?,?,0)""",
            (
                eid,
                version + 1,
                title,
                amount,
                payer,
                json.dumps(split),
                "Equal" if shares is None else "Custom",
                category,
                day,
            ),
        )
        return eid

    def delete_expense(self, gid, eid, version):
        with self.transaction() as db:
            self.current_revision(db, gid, eid, version)
            db.execute(
                """INSERT INTO revisions(expense_id,version,title,amount,payer,shares,mode,category,day,deleted)
                SELECT expense_id,version+1,title,amount,payer,shares,mode,category,day,1 FROM revisions
                WHERE expense_id=? AND version=?""",
                (eid, version),
            )

    def pay(self, gid, sender, receiver, amount, day):
        valid_amount(amount)
        day = date.fromisoformat(day).isoformat()
        with self.transaction() as db:
            members = self.group(db, gid)["members"]
            if sender == receiver or sender not in members or receiver not in members:
                raise ValueError("Choose two different members for the payment.")
            db.execute(
                "INSERT INTO payments(group_id,sender,receiver,amount,day) VALUES (?,?,?,?,?)",
                (gid, sender, receiver, amount, day),
            )
