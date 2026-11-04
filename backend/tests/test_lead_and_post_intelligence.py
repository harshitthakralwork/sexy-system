from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.core.database import session_scope
from app.modules.social.classification import classify
from app.modules.social.models import SocialContent, SocialContentUserAnnotation, SocialPlatform
from tests.conftest import Session


def test_classification_engine_categories_and_scoring():
    # 1. Buying intent post -> Service needed, high score
    text_hire = "We are looking to hire a senior Python engineer to build an automated scraping pipeline. Budget $5k."
    res_hire = classify(text_hire)
    assert res_hire.category in ("Freelancer hiring", "Service needed")
    assert res_hire.score >= 50
    assert res_hire.confidence > 0
    assert len(res_hire.matched_terms) > 0
    assert "ai-automation" in res_hire.service_tags or "web-development" in res_hire.service_tags

    # 2. Recommendation request
    text_rec = "Can anyone recommend a reliable SEO agency or marketing consultant for our local bakery?"
    res_rec = classify(text_rec)
    assert res_rec.category in ("Recommendation request", "Service needed")
    assert res_rec.score >= 30
    assert "seo-marketing" in res_rec.service_tags

    # 3. Negative signals / job seeker / self promotion
    text_seeker = "I am a freelance web developer available for hire! Check out my portfolio and hire me for your next gig."
    res_seeker = classify(text_seeker)
    assert res_seeker.score < res_hire.score
    assert len(res_seeker.negative_signals) > 0

    # 4. Irrelevant content
    text_noise = "Just had the best coffee in the city this morning. Beautiful sunshine!"
    res_noise = classify(text_noise)
    assert res_noise.category in ("Not relevant", "General discussion")
    assert res_noise.score <= 30


def test_user_annotation_isolation(session_account: Session):
    content_id = uuid.uuid4()
    owner_id = uuid.UUID(session_account.user_id)

    async def seed_data():
        async with session_scope() as db:
            plat = SocialPlatform(
                name="Reddit Test",
                slug=f"reddit-test-{uuid.uuid4().hex[:6]}",
                adapter_key="reddit",
                is_enabled=True,
                health_status="working",
            )
            db.add(plat)
            await db.flush()

            content = SocialContent(
                id=content_id,
                owner_user_id=owner_id,
                platform_id=plat.id,
                external_id="ext-12345",
                content_url="https://reddit.com/r/forhire/comments/123",
                canonical_url="https://reddit.com/r/forhire/comments/123",
                content_text="Looking for a web dev to build a dashboard",
                discovered_at=datetime.now(UTC),
                classification="Service needed",
                confidence_score=0.88,
                classification_score=85,
                service_tags=["web-development"],
            )
            db.add(content)

            ann = SocialContentUserAnnotation(
                content_id=content_id,
                owner_user_id=owner_id,
                lead_status="contacted",
                is_hot=True,
                user_note="Sent proposal via email on Monday",
                quoted_customer_need="Needs a dashboard by Friday",
                services_to_sell=["web-development"],
            )
            db.add(ann)
            await db.flush()

    asyncio.run(seed_data())

    # Now verify via API that annotations are retrieved
    resp = session_account.api.get(f"/api/v1/social/posts/{content_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(content_id)
    assert data["user_annotation"]["lead_status"] == "contacted"
    assert data["user_annotation"]["is_hot"] is True
    assert data["user_annotation"]["user_note"] == "Sent proposal via email on Monday"
    assert data["user_annotation"]["quoted_customer_need"] == "Needs a dashboard by Friday"

    # Update annotation via PATCH
    patch_resp = session_account.api.patch(
        f"/api/v1/social/posts/{content_id}/annotation",
        json={
            "lead_status": "qualified",
            "is_hot": True,
            "user_note": "Client responded positively!",
            "services_to_sell": ["web-development", "seo-marketing"],
        },
        headers=session_account.csrf_headers(),
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["lead_status"] == "qualified"
    assert updated["user_note"] == "Client responded positively!"

    # List posts filter
    list_resp = session_account.api.get("/api/v1/social/posts?lead_status=qualified&is_hot=true")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert any(p["id"] == str(content_id) for p in list_data["items"])

    # Leads dashboard
    dash_resp = session_account.api.get("/api/v1/social/leads-dashboard")
    assert dash_resp.status_code == 200
    dash_data = dash_resp.json()
    assert "demand_posts_found" in dash_data
    assert "high_confidence_leads" in dash_data
    assert "classification_distribution" in dash_data
    assert "posts_per_day" in dash_data
