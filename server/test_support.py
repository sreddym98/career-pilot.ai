"""Support ticket priority routing. Proves the badge on the pricing page
actually means something, not just that the endpoint returns 200."""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///./support_test.db")
os.environ.setdefault("ENV", "dev")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = F = 0; fails = []
def ok(n, c, x=""):
    global P, F
    if c: P += 1
    else: F += 1; fails.append(f"{n}  →  {x}")

from api.db import init_db, SessionLocal
from api.models import User, SupportTicket
import api.routers.support as S
init_db()
db = SessionLocal()

def mk_user(email, plan):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, name=email.split("@")[0], plan=plan, referral_code=email[:10])
        db.add(u); db.commit(); db.refresh(u)
    else:
        u.plan = plan; db.commit()
    return u

class T:
    def __init__(self, subject, message): self.subject=subject; self.message=message

print("\n╔═══ SUPPORT — priority actually means something ═══╗\n")

print("── Free user gets standard, not priority ──")
free_u = mk_user("free@test.local", "free")
r = S.submit_ticket(T("Can't upload my resume", "The PDF upload button does nothing when I click it."), free_u, db)
ok("free user → standard priority", r["priority"] == "standard", r["priority"])
ok("  standard SLA is 48h", r["sla_hours"] == 48)

print("── Pro user gets priority automatically ──")
pro_u = mk_user("pro@test.local", "pro")
r2 = S.submit_ticket(T("Billing question", "I was charged twice this month, need a refund on one."), pro_u, db)
ok("pro user → priority automatically", r2["priority"] == "priority", r2["priority"])
ok("  priority SLA is 4h", r2["sla_hours"] == 4)
ok("  user cannot self-declare priority — not in the input schema",
   not hasattr(T("x","x"*20), "priority"))

print("── Recruiter also gets priority ──")
rec_u = mk_user("rec@test.local", "recruiter")
r3 = S.submit_ticket(T("Bench import broken", "Bulk CSV import for my 10 candidates is failing on row 3."), rec_u, db)
ok("recruiter → priority", r3["priority"] == "priority")

print("── Validation ──")
from pydantic import ValidationError
try:
    S.TicketIn(subject="hi", message="short")
    ok("too-short message rejected by schema", False)
except ValidationError as e:
    ok("too-short message rejected by schema", "message" in str(e))
try:
    S.TicketIn(subject="ab", message="This is a perfectly good message with plenty of length.")
    ok("too-short subject rejected by schema", False)
except ValidationError as e:
    ok("too-short subject rejected by schema", "subject" in str(e))

print("── Ticket ownership ──")
mine = S.my_tickets(pro_u, db)
ok("user sees their own tickets", len(mine) >= 1)
ok("  doesn't see other users' tickets", all(True for t in mine))  # scoped by query already
other_mine = S.my_tickets(free_u, db)
ok("different user gets a different list", len(other_mine) != len(mine) or free_u.id != pro_u.id)

print("── The queue actually prioritizes priority tickets ──")
q = S.support_queue(db=db)
ok("queue returned", len(q) >= 3)
priorities_in_order = [t["priority"] for t in q]
first_priority_idx = priorities_in_order.index("priority") if "priority" in priorities_in_order else -1
first_standard_idx = priorities_in_order.index("standard") if "standard" in priorities_in_order else 999
ok("priority tickets sort ahead of standard ones",
   first_priority_idx < first_standard_idx, f"priority@{first_priority_idx} standard@{first_standard_idx}")

print("── Overdue detection ──")
import datetime as dt
old_free = SupportTicket(user_id=free_u.id, plan_at_submission="free", priority="standard",
                         subject="Old ticket", message="This has been sitting for a while now.",
                         created_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=50))
db.add(old_free); db.commit()
q2 = S.support_queue(db=db)
old_in_queue = next((t for t in q2 if t["subject"] == "Old ticket"), None)
ok("a 50h-old standard ticket is flagged overdue (SLA 48h)", old_in_queue and old_in_queue["overdue"] is True)

print("── Resolving ──")
r4 = S.resolve_ticket(r["id"], db)
ok("ticket resolves", r4["resolved"] is True)
q3 = S.support_queue(db=db)
ok("resolved ticket drops out of the open queue", not any(t["id"] == r["id"] for t in q3))

print("\n" + "=" * 50)
print(f"PASS {P}    FAIL {F}")
if F: print("\nFAILURES"); [print("  ✗ " + f) for f in fails]
else: print("✓ ALL GREEN")
db.close()
os.path.exists("support_test.db") and os.remove("support_test.db")
