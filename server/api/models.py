# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
import uuid, datetime as dt
from sqlalchemy import (Column, String, Text, Boolean, Integer, Date, DateTime,
                        ForeignKey, SmallInteger, JSON, Index, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY as PG_ARRAY, JSONB as PG_JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator, TEXT
import json as _json

# ── Portable types: real Postgres types in prod, JSON-in-TEXT on SQLite ──
class UUIDStr(TypeDecorator):
    impl = String; cache_ok = True
    def load_dialect_impl(self, d):
        return d.type_descriptor(PG_UUIDStr()) if d.name == "postgresql" else d.type_descriptor(String(36))

class StrArray(TypeDecorator):
    impl = TEXT; cache_ok = True
    def load_dialect_impl(self, d):
        return d.type_descriptor(PG_StrArray()) if d.name == "postgresql" else d.type_descriptor(TEXT)
    def process_bind_param(self, v, d):
        if v is None: return None
        return v if d.name == "postgresql" else _json.dumps(list(v))
    def process_result_value(self, v, d):
        if v is None: return []
        return v if d.name == "postgresql" else _json.loads(v)

class JSONish(TypeDecorator):
    impl = TEXT; cache_ok = True
    def load_dialect_impl(self, d):
        return d.type_descriptor(PG_JSONB) if d.name == "postgresql" else d.type_descriptor(TEXT)
    def process_bind_param(self, v, d):
        if v is None: return None
        return v if d.name == "postgresql" else _json.dumps(v)
    def process_result_value(self, v, d):
        if v is None: return None
        return v if d.name == "postgresql" else _json.loads(v)

Base = declarative_base()
def _id(): return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    # 'seeker' finds their own next role; 'recruiter' places other people.
    # Chosen at signup and not switchable — the two are separate products that
    # happen to share a job feed. Authorization reads THIS column, never a
    # token claim, so an account is exactly what the database says it is.
    account_type = Column(String, nullable=False, default="seeker", index=True)
    # NULL for accounts that only ever signed in through a hosted provider
    # (Supabase/Firebase). Never populated from anything but api/passwords.py.
    password_hash = Column(String)
    slug = Column(String, unique=True, index=True)      # careerpilot.ai/santoshreddy
    headline = Column(String)
    location = Column(String)
    phone = Column(String)
    linkedin = Column(String)
    summary = Column(Text)
    work_auth = Column(StrArray(), default=list)     # {'h1b'} etc.
    plan = Column(String, default="free")
    stripe_customer = Column(String)
    stripe_subscription = Column(String)
    credits_used = Column(Integer, default=0)
    credits_reset_at = Column(DateTime(timezone=True))
    referral_code = Column(String, unique=True, index=True)
    referred_by = Column(UUIDStr(), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())

    positions = relationship("Position", back_populates="user",
                             cascade="all, delete-orphan",
                             order_by="Position.started_on.desc()")


class Position(Base):
    """Durations are DERIVED from these dates, never stored.
    Storing a duration means it goes stale the moment the month rolls over."""
    __tablename__ = "positions"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    started_on = Column(Date, nullable=False)
    finished_on = Column(Date)                          # NULL = current role
    location = Column(String)
    bullets = Column(JSONish(), default=list)
    user = relationship("User", back_populates="positions")

    @property
    def months(self) -> int:
        end = self.finished_on or dt.date.today()
        return max(0, (end.year - self.started_on.year) * 12
                      + (end.month - self.started_on.month) + 1)

    @property
    def duration_label(self) -> str:
        m = self.months
        y, mo = divmod(m, 12)
        parts = []
        if y:  parts.append(f"{y} yr" + ("s" if y > 1 else ""))
        if mo: parts.append(f"{mo} mo" + ("s" if mo > 1 else ""))
        return " ".join(parts) or "0 mos"


class UserSkill(Base):
    __tablename__ = "user_skills"
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    skill = Column(String, primary_key=True)
    is_top = Column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"
    fingerprint = Column(String, primary_key=True)      # dedup key from ingest
    source = Column(String, nullable=False)
    source_id = Column(String)
    company = Column(String, nullable=False, index=True)
    company_type = Column(String)                        # employer | staffing
    is_fortune500 = Column(Boolean, default=False)
    title = Column(String, nullable=False)
    location = Column(String)
    work_mode = Column(String)                           # remote | hybrid | onsite
    employment = Column(String)                          # fulltime | contract
    description = Column(Text)
    apply_url = Column(String)
    comp_min = Column(Integer); comp_max = Column(Integer); comp_unit = Column(String)
    exp_min = Column(Integer);  exp_max = Column(Integer)
    # 'y' accepted | 'n' excluded | 'u' not stated. Default 'u' — see visa_parse.py
    visa_usc = Column(String(1), default="u")
    visa_gc  = Column(String(1), default="u")
    visa_h1b = Column(String(1), default="u")
    visa_opt = Column(String(1), default="u")
    role_family = Column(String, index=True)             # taxonomy id — the moat
    career_field = Column(String, index=True)
    required_skills = Column(StrArray())
    posted_at = Column(DateTime(timezone=True))
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    seen_count = Column(Integer, default=1)
    relisted = Column(Boolean, default=False)
    active = Column(Boolean, default=True, index=True)

    __table_args__ = (
        Index("ix_jobs_browse", "active", "role_family", "posted_at"),
        
    )


class Application(Base):
    __tablename__ = "applications"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # NULL for anything applied to outside our feed — a posting someone found
    # on LinkedIn still belongs in their tracker, and a FK to a job we never
    # ingested would make that impossible to record.
    fingerprint = Column(String, ForeignKey("jobs.fingerprint"))
    # Denormalised on purpose. The tracker has to keep reading correctly after
    # a posting is taken down and its jobs row goes inactive or is pruned.
    company = Column(String, nullable=False, default="")
    title = Column(String, nullable=False, default="")
    location = Column(String)
    note = Column(String)             # "Call scheduled", "Negotiating rate"
    status = Column(String, default="queued")
    # queued|preparing|needs_input|ready|submitted|responded|interview|selected|rejected
    blocker = Column(String)          # salary | sponsorship | suspicious_repost
    tailored_resume = Column(JSONish())
    cover_letter = Column(Text)
    form_fields = Column(JSONish())
    applied_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SupportTicket(Base):
    """One row per support request. `priority` is set from user.plan at the
    moment of submission — Pro/Recruiter get 'priority', Free gets
    'standard'. This is the actual mechanism behind the "Priority support"
    line on the pricing page; without this table that badge is empty."""
    __tablename__ = "support_tickets"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_at_submission = Column(String, nullable=False)
    priority = Column(String, nullable=False, default="standard")  # priority | standard
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String, default="open")  # open | answered | closed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))


class Evaluation(Base):
    """One paid evaluation per checkout session. `report` is null until the
    webhook confirms payment — see api/routers/evaluation.py. Nothing here
    is shown to the user before that."""
    __tablename__ = "evaluations"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stripe_session_id = Column(String, unique=True)
    paid = Column(Boolean, default=False)
    report = Column(JSONish())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True))


class AICache(Base):
    """The single most important table for margin.
    Same resume + same JD = same answer, served free."""
    __tablename__ = "ai_cache"
    cache_key = Column(String, primary_key=True)
    result = Column(JSONish(), nullable=False)
    hits = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Integration(Base):
    """A provider connection owned by one user.

    The credential is encrypted before storage. The status field lets the
    frontend distinguish "not configured", "needs verification", and a real
    provider-confirmed connection without exposing a token to the browser.
    """
    __tablename__ = "integrations"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False)  # gmail | phone
    status = Column(String, nullable=False, default="pending")
    credential = Column(Text)
    metadata_json = Column(JSONish())
    verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_integrations_user_provider"),)


class Course(Base):
    __tablename__ = "courses"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    name = Column(String); provider = Column(String); url = Column(String)
    price_cents = Column(Integer, default=0)
    kind = Column(String)             # course | cert | path
    hours = Column(Integer)
    skills = Column(StrArray())
    description = Column(Text)
    


class Connection(Base):
    __tablename__ = "connections"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    user_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name = Column(String); role = Column(String); company = Column(String, index=True)
    degree = Column(SmallInteger)     # 1 | 2 | 3
    how_known = Column(String)


class Referral(Base):
    __tablename__ = "referrals"
    id = Column(UUIDStr(), primary_key=True, default=_id)
    referrer_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    referee_id = Column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"))
    email_invited = Column(String)
    status = Column(String, default="invited")   # invited | joined | active
    qualified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
