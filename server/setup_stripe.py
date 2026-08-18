# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Create the CareerPilot products and prices in your Stripe account.

    export STRIPE_SECRET_KEY=sk_test_...
    python setup_stripe.py

Idempotent — safe to run repeatedly. It looks for existing products by
lookup_key before creating anything, so a second run just prints the IDs.

Outputs the exact .env lines to paste.
"""
import os, sys

try:
    import stripe
except ImportError:
    sys.exit("pip install stripe")

KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
if not KEY:
    sys.exit("Set STRIPE_SECRET_KEY first:\n  export STRIPE_SECRET_KEY=sk_test_...")
if KEY.startswith("pk_"):
    sys.exit("That's the publishable key. You need the secret key (sk_test_... or sk_live_...).")

stripe.api_key = KEY
LIVE = KEY.startswith("sk_live_")

PRODUCT = {
    "name": "careerpilot.ai Pro",
    "description": (
        "400 applications a month — tailored resume and cover letter for "
        "each — plus Autopilot, pre-filled answers, and the browser extension."
    ),
}

RECRUITER_PRODUCT = {
    "name": "careerpilot.ai Recruiter — 10 seats",
    "description": (
        "Manage up to 10 candidates on one bench: fit-matched ranking per "
        "role, unlimited submissions, shared job feed."
    ),
}

# Separate product — a one-time purchase, not a subscription. Priced to be
# an easy first "yes" before anyone commits to Pro.
EVAL_PRODUCT = {
    "name": "careerpilot.ai Profile Evaluation",
    "description": (
        "A one-time AI review of your resume, experience, career goals, and "
        "visa status — with a readiness score and specific next steps."
    ),
}

PRICES = [
    {
        "lookup_key": "careerpilot_profile_eval",
        "nickname": "Profile Evaluation — one time",
        "unit_amount": 500,           # $5.00
        "interval": None,             # one-time, not recurring
        "env": "STRIPE_PRICE_EVAL",
        "product": "eval",
    },
    {
        # List price is $149.99 — this is the launch OFFER price actually
        # charged. Both figures are shown on the pricing page; only this
        # one goes to Stripe, since that's what the customer pays.
        "lookup_key": "careerpilot_pro_monthly",
        "nickname": "Pro — $119.99/mo (offer, list $149.99)",
        "unit_amount": 11999,         # $119.99
        "interval": "month",
        "env": "STRIPE_PRICE_PRO_MONTHLY",
        "product": "pro",
    },
    {
        # $99.99/mo, billed every 3 months as one $299.97 charge —
        # matches the "Save $20/mo" term chip on the pricing page exactly.
        "lookup_key": "careerpilot_pro_3mo",
        "nickname": "Pro — 3-month term ($99.99/mo, billed quarterly)",
        "unit_amount": 29997,         # $299.97 every 3 months
        "interval": "month",
        "interval_count": 3,
        "env": "STRIPE_PRICE_PRO_3MO",
        "product": "pro",
    },
    {
        # $89.99/mo, billed every 6 months as one $539.94 charge —
        # matches the "Save $30/mo" term chip exactly.
        "lookup_key": "careerpilot_pro_6mo",
        "nickname": "Pro — 6-month term ($89.99/mo, billed semi-annually)",
        "unit_amount": 53994,         # $539.94 every 6 months
        "interval": "month",
        "interval_count": 6,
        "env": "STRIPE_PRICE_PRO_6MO",
        "product": "pro",
    },
    {
        "lookup_key": "careerpilot_recruiter_10",
        "nickname": "Recruiter — 10 seats",
        "unit_amount": 16999,         # $169.99
        "interval": "month",
        "env": "STRIPE_PRICE_RECRUITER",
        "product": "recruiter",
    },
]


def find_or_create_product():
    for p in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        if p.metadata.get("app") == "careerpilot" and p.metadata.get("tier") == "pro":
            print(f"  · product exists       {p.id}")
            return p
    p = stripe.Product.create(
        name=PRODUCT["name"],
        description=PRODUCT["description"],
        metadata={"app": "careerpilot", "tier": "pro"},
    )
    print(f"  ✓ product created      {p.id}")
    return p


def find_or_create_price(product, spec):
    try:
        found = stripe.Price.list(lookup_keys=[spec["lookup_key"]], limit=1)
        if found.data:
            pr = found.data[0]
            print(f"  · price exists         {pr.id}   {spec['nickname']}")
            return pr
    except Exception:
        pass
    kwargs = dict(product=product.id, lookup_key=spec["lookup_key"],
                  nickname=spec["nickname"], unit_amount=spec["unit_amount"],
                  currency="usd", metadata={"app": "careerpilot"})
    if spec["interval"]:
        kwargs["recurring"] = {"interval": spec["interval"]}
        if spec.get("interval_count"):
            kwargs["recurring"]["interval_count"] = spec["interval_count"]
    pr = stripe.Price.create(**kwargs)
    print(f"  ✓ price created        {pr.id}   {spec['nickname']}")
    return pr


def find_or_create_eval_product():
    for p in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        if p.metadata.get("app") == "careerpilot" and p.metadata.get("tier") == "eval":
            print(f"  · eval product exists  {p.id}")
            return p
    p = stripe.Product.create(name=EVAL_PRODUCT["name"], description=EVAL_PRODUCT["description"],
                              metadata={"app": "careerpilot", "tier": "eval"})
    print(f"  ✓ eval product created {p.id}")
    return p


def find_or_create_recruiter_product():
    for p in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        if p.metadata.get("app") == "careerpilot" and p.metadata.get("tier") == "recruiter":
            print(f"  · recruiter product exists  {p.id}")
            return p
    p = stripe.Product.create(name=RECRUITER_PRODUCT["name"], description=RECRUITER_PRODUCT["description"],
                              metadata={"app": "careerpilot", "tier": "recruiter"})
    print(f"  ✓ recruiter product created {p.id}")
    return p


def main():
    mode = "LIVE" if LIVE else "TEST"
    print(f"\nStripe setup — {mode} mode")
    if LIVE:
        print("  ⚠ These are real charges. Ctrl-C now if that wasn't intended.")
    print()

    try:
        acct = stripe.Account.retrieve()
        print(f"  account: {acct.get('settings',{}).get('dashboard',{}).get('display_name') or acct.id}")
    except stripe.error.AuthenticationError:
        sys.exit("  ✗ Invalid key. Check you copied the whole thing.")
    except Exception as e:
        print(f"  (couldn't read account name: {e})")
    print()

    product = find_or_create_product()
    eval_product = find_or_create_eval_product()
    recruiter_product = find_or_create_recruiter_product()
    products = {"eval": eval_product, "pro": product, "recruiter": recruiter_product}
    out = {}
    for spec in PRICES:
        pr = find_or_create_price(products[spec["product"]], spec)
        out[spec["env"]] = pr.id

    # Customer portal — lets people cancel themselves, which the pricing page promises
    try:
        cfgs = stripe.billing_portal.Configuration.list(limit=1)
        if not cfgs.data:
            stripe.billing_portal.Configuration.create(
                business_profile={"headline": "careerpilot.ai"},
                features={
                    "customer_update": {"enabled": True, "allowed_updates": ["email", "address"]},
                    "invoice_history": {"enabled": True},
                    "payment_method_update": {"enabled": True},
                    "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
                },
            )
            print("  ✓ customer portal      configured (self-serve cancel enabled)")
        else:
            print("  · customer portal      already configured")
    except Exception as e:
        print(f"  ⚠ portal setup skipped: {e}")

    print("\n" + "─" * 58)
    print("Paste into your .env:\n")
    print(f"STRIPE_SECRET_KEY={KEY[:12]}…            # the key you used")
    for k, v in out.items():
        print(f"{k}={v}")
    print("STRIPE_WEBHOOK_SECRET=whsec_…              # from the next step")
    print("─" * 58)

    print("""
NEXT — the webhook. Without it, someone pays and never gets upgraded.

  Local testing:
    stripe listen --forward-to localhost:8000/api/billing/webhook
    → prints a whsec_… — put that in .env

  Production:
    Dashboard → Developers → Webhooks → Add endpoint
    URL:    https://api.yourdomain.com/api/billing/webhook
    Events: checkout.session.completed
            customer.subscription.updated
            customer.subscription.deleted
            invoice.payment_failed

  Then verify end to end:
    stripe trigger checkout.session.completed
    → your API should flip that user's plan to 'pro'

Test cards (test mode only):
  4242 4242 4242 4242   succeeds
  4000 0000 0000 9995   declined — insufficient funds
  4000 0025 0000 3155   requires 3D Secure authentication
""")


if __name__ == "__main__":
    main()
