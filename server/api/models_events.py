# careerpilot.ai — Copyright (c) 2026 Santosh Reddy Mamindla.
# Proprietary and confidential. See LICENSE.
"""Webhook event ledger. Lives outside models.py so it can be added without
touching the shared model file; it registers on the same Base, so init_db()
creates it as soon as this module has been imported (main.py and the billing
router both import it)."""
import datetime as dt
from sqlalchemy import Column, String, DateTime
from api.models import Base


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    id = Column(String(255), primary_key=True)          # Stripe event id
    type = Column(String(100))
    created_at = Column(DateTime(timezone=True),
                        default=lambda: dt.datetime.now(dt.timezone.utc))
