# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from api.db import get_db
from api.auth import current_user
from api.models import User
from api.settings import settings

router = APIRouter(prefix="/api/billing", tags=["billing"])
stripe.api_key = settings.STRIPE_SECRET_KEY
PRICES = {"pro": settings.STRIPE_PRICE_PRO_MONTHLY,
          "recruiter": settings.STRIPE_PRICE_RECRUITER}
# Term-length variants of Pro — same product, billed less often at a
# discount. Not in PRICES above because they're only reachable via the
# `term` query param, not a bare plan name.
PRO_TERM_PRICES = {1: settings.STRIPE_PRICE_PRO_MONTHLY,
                   3: settings.STRIPE_PRICE_PRO_3MO,
                   6: settings.STRIPE_PRICE_PRO_6MO}
EVAL_PRICE = "eval"   # separate namespace — one-time, not a plan


def _require_config():
    """Better a clear 503 than a cryptic Stripe error the user can't act on."""
    missing = [k for k, v in {
        "STRIPE_SECRET_KEY": settings.STRIPE_SECRET_KEY,
        "STRIPE_PRICE_PRO_MONTHLY": settings.STRIPE_PRICE_PRO_MONTHLY,
        "STRIPE_PRICE_RECRUITER": settings.STRIPE_PRICE_RECRUITER,
    }.items() if not v]
    if missing:
        raise HTTPException(503, f"Billing not configured — missing {', '.join(missing)}. "
                                 f"Run: python setup_stripe.py")


@router.get("/config")
def config():
    """What the frontend needs. Publishable key only — never the secret."""
    return {"configured": bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_PRO_MONTHLY),
            "publishable_key": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
            "plans": {
                "pro": {"amount": 11999, "list_amount": 14999, "interval": "month",
                        "label": "$119.99/mo", "list_label": "$149.99/mo",
                        "applications_per_month": 400},
                "recruiter": {"amount": 16999, "interval": "month",
                              "label": "$169.99/mo", "seats": 10},
            }}


@router.post("/checkout")
def checkout(plan: str, user: User = Depends(current_user), db: Session = Depends(get_db), term: int = 1):
    _require_config()
    if plan not in PRICES:
        raise HTTPException(400, "Unknown plan")
    price_id = PRICES[plan]
    if plan == "pro":
        if term not in PRO_TERM_PRICES:
            raise HTTPException(400, "term must be 1, 3, or 6 months")
        price_id = PRO_TERM_PRICES[term]
        if not price_id:
            raise HTTPException(503, f"The {term}-month Pro price isn't configured yet — run setup_stripe.py")
    if not user.stripe_customer:
        c = stripe.Customer.create(email=user.email, name=user.name)
        user.stripe_customer = c.id
        db.commit()
    s = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/?upgraded=1",
        cancel_url=f"{settings.FRONTEND_URL}/?pricing=1",
        client_reference_id=user.id,
        allow_promotion_codes=True,
    )
    return {"url": s.url}


@router.post("/checkout-evaluation")
def checkout_evaluation(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """One-time $5 charge. Separate flow from /checkout: mode="payment" not
    "subscription", so it fires payment_intent.succeeded rather than
    checkout.session.completed with a subscription attached."""
    if not settings.STRIPE_PRICE_EVAL:
        raise HTTPException(503, "Evaluation isn't configured yet — run: python setup_stripe.py")
    if not user.stripe_customer:
        c = stripe.Customer.create(email=user.email, name=user.name)
        user.stripe_customer = c.id
        db.commit()

    from api.models import Evaluation
    ev = Evaluation(user_id=user.id)
    db.add(ev); db.commit(); db.refresh(ev)

    s = stripe.checkout.Session.create(
        mode="payment",
        customer=user.stripe_customer,
        line_items=[{"price": settings.STRIPE_PRICE_EVAL, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/?eval_paid=1&eval_id={ev.id}",
        cancel_url=f"{settings.FRONTEND_URL}/?eval_cancelled=1",
        client_reference_id=ev.id,   # the EVALUATION id, not the user id
        metadata={"user_id": user.id, "kind": "evaluation"},
    )
    ev.stripe_session_id = s.id
    db.commit()
    return {"url": s.url, "evaluation_id": ev.id}


@router.post("/portal")
def portal(user: User = Depends(current_user)):
    """Self-serve cancel. No retention call, no email required —
    that's what the pricing page promises, so honour it."""
    if not user.stripe_customer:
        raise HTTPException(400, "No subscription")
    s = stripe.billing_portal.Session.create(
        customer=user.stripe_customer, return_url=settings.FRONTEND_URL)
    return {"url": s.url}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "STRIPE_WEBHOOK_SECRET not set — run: stripe listen "
                                 "--forward-to localhost:8000/api/billing/webhook")
    try:
        # WITHOUT this verification anyone can POST themselves a free Pro plan.
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(400, f"Bad signature: {e}")

    t, obj = event["type"], event["data"]["object"]

    if t == "checkout.session.completed" and obj.get("mode") == "payment" \
            and (obj.get("metadata") or {}).get("kind") == "evaluation":
        from api.models import Evaluation
        ev = db.query(Evaluation).get(obj.get("client_reference_id"))
        if ev and not ev.paid:
            import datetime as _dt
            ev.paid = True
            ev.paid_at = _dt.datetime.now(_dt.timezone.utc)
            db.commit()
            print(f"[billing] evaluation {ev.id} paid")

    elif t == "checkout.session.completed":
        u = db.query(User).get(obj.get("client_reference_id"))
        if u:
            u.stripe_subscription = obj.get("subscription")
            sub = stripe.Subscription.retrieve(obj["subscription"])
            price = sub["items"]["data"][0]["price"]["id"]
            u.plan = "recruiter" if price == PRICES["recruiter"] else "pro"
            db.commit()

    elif t in ("customer.subscription.updated", "customer.subscription.deleted"):
        u = db.query(User).filter(User.stripe_customer == obj["customer"]).first()
        if u:
            if t.endswith("deleted") or obj["status"] in ("canceled", "unpaid"):
                u.plan = "free"
            else:
                price = obj["items"]["data"][0]["price"]["id"]
                u.plan = "recruiter" if price == PRICES["recruiter"] else "pro"
            db.commit()

    elif t == "invoice.payment_failed":
        u = db.query(User).filter(User.stripe_customer == obj["customer"]).first()
        if u:
            # Stripe retries for a few days before cancelling. Don't downgrade
            # yet — the subscription.deleted event handles that.
            print(f"[billing] payment failed for {u.email} — Stripe will retry")

    else:
        print(f"[billing] unhandled event: {t}")

    return {"received": True}
