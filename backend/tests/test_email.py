"""Phase 5: email module — accounts, campaigns, drafts, suppression, send guards.

The send path is tested up to the provider boundary: no SMTP credentials exist in
this environment, so the honest outcomes are "blocked" (no account / not connected /
provider not configured) and "suppressed". Anything else would be a fake send.
"""

from __future__ import annotations

from collections.abc import Callable

from tests.conftest import Session


def _create_account(account: Session, *, email: str = "me@sparkxflow.dev") -> dict:
    response = account.api.post(
        "/api/v1/email/accounts",
        json={"provider": "smtp", "email_address": email},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_draft(account: Session, *, recipient: str, **extra) -> dict:
    response = account.api.post(
        "/api/v1/email/messages",
        json={"recipient_email": recipient, **extra},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Accounts ---------------------------------------------------------------


def test_account_crud(session_account: Session) -> None:
    created = _create_account(session_account)
    assert created["provider"] == "smtp"
    assert created["email_address"] == "me@sparkxflow.dev"
    assert created["status"] == "pending"
    assert created["connected_at"] is None

    listed = session_account.api.get("/api/v1/email/accounts")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    connected = session_account.api.patch(
        f"/api/v1/email/accounts/{created['id']}",
        json={"status": "connected"},
        headers=session_account.csrf_headers(),
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["status"] == "connected"
    assert connected.json()["connected_at"] is not None

    deleted = session_account.api.delete(
        f"/api/v1/email/accounts/{created['id']}",
        headers=session_account.csrf_headers(),
    )
    assert deleted.status_code == 204
    assert session_account.api.get("/api/v1/email/accounts").json()["total"] == 0


def test_duplicate_account_conflicts(session_account: Session) -> None:
    _create_account(session_account)
    response = session_account.api.post(
        "/api/v1/email/accounts",
        json={"provider": "smtp", "email_address": "me@sparkxflow.dev"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 409, response.text


def test_unknown_provider_rejected(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/email/accounts",
        json={"provider": "carrier_pigeon", "email_address": "me@sparkxflow.dev"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


# --- Campaigns --------------------------------------------------------------


def test_campaign_crud(session_account: Session) -> None:
    created = session_account.api.post(
        "/api/v1/email/campaigns",
        json={"name": "Q4 outreach"},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"

    patched = session_account.api.patch(
        f"/api/v1/email/campaigns/{created.json()['id']}",
        json={"status": "active"},
        headers=session_account.csrf_headers(),
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "active"

    assert session_account.api.get("/api/v1/email/campaigns").json()["total"] == 1
    deleted = session_account.api.delete(
        f"/api/v1/email/campaigns/{created.json()['id']}",
        headers=session_account.csrf_headers(),
    )
    assert deleted.status_code == 204


# --- Drafts and the approval gate ------------------------------------------


def test_manual_draft_starts_as_draft_not_gated(session_account: Session) -> None:
    message = _create_draft(
        session_account,
        recipient="owner@sparkcafe.in",
        subject="Hello",
        body="Body text",
    )
    assert message["status"] == "draft"
    assert message["recipient_email"] == "owner@sparkcafe.in"


def test_approve_moves_draft_to_approved(session_account: Session) -> None:
    message = _create_draft(session_account, recipient="owner@sparkcafe.in")
    approved = session_account.api.post(
        f"/api/v1/email/messages/{message['id']}/approve",
        headers=session_account.csrf_headers(),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_at"] is not None


def test_send_unapproved_message_is_refused(session_account: Session) -> None:
    message = _create_draft(session_account, recipient="owner@sparkcafe.in")
    response = session_account.api.post(
        f"/api/v1/email/messages/{message['id']}/send",
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 409, response.text


def test_send_without_account_blocks_honestly(session_account: Session) -> None:
    message = _create_draft(session_account, recipient="owner@sparkcafe.in")
    session_account.api.post(
        f"/api/v1/email/messages/{message['id']}/approve",
        headers=session_account.csrf_headers(),
    )
    sent = session_account.api.post(
        f"/api/v1/email/messages/{message['id']}/send",
        headers=session_account.csrf_headers(),
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "blocked"
    assert "account" in body["error"]

    events = session_account.api.get(f"/api/v1/email/messages/{message['id']}/events")
    assert events.status_code == 200
    assert any(event["event_type"] == "failed" for event in events.json())


# --- Suppression ------------------------------------------------------------


def test_suppressed_address_refused_at_draft(session_account: Session) -> None:
    added = session_account.api.post(
        "/api/v1/email/suppression",
        json={"email_address": "noreply@spam.in", "reason": "bounced"},
        headers=session_account.csrf_headers(),
    )
    assert added.status_code == 201, added.text
    assert added.json()["normalized_email"] == "noreply@spam.in"

    response = session_account.api.post(
        "/api/v1/email/messages",
        json={"recipient_email": "noreply@spam.in"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 409, response.text


def test_suppression_add_is_idempotent(session_account: Session) -> None:
    payload = {"email_address": "dup@spam.in"}
    first = session_account.api.post(
        "/api/v1/email/suppression", json=payload, headers=session_account.csrf_headers()
    )
    second = session_account.api.post(
        "/api/v1/email/suppression", json=payload, headers=session_account.csrf_headers()
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert session_account.api.get("/api/v1/email/suppression").json()["total"] == 1


def test_suppression_remove(session_account: Session) -> None:
    added = session_account.api.post(
        "/api/v1/email/suppression",
        json={"email_address": "gone@spam.in"},
        headers=session_account.csrf_headers(),
    ).json()
    removed = session_account.api.delete(
        f"/api/v1/email/suppression/{added['id']}",
        headers=session_account.csrf_headers(),
    )
    assert removed.status_code == 204
    assert session_account.api.get("/api/v1/email/suppression").json()["total"] == 0


# --- Cross-owner isolation --------------------------------------------------


def test_cross_owner_email_isolation(
    session_account: Session, make_account: Callable[[], Session]
) -> None:
    owner = session_account
    other = make_account()

    _create_account(owner, email="me@sparkxflow.dev")
    _create_draft(owner, recipient="owner@sparkcafe.in")

    assert other.api.get("/api/v1/email/accounts").json()["total"] == 0
    assert other.api.get("/api/v1/email/messages").json()["total"] == 0

    message_id = owner.api.get("/api/v1/email/messages").json()["items"][0]["id"]
    assert other.api.get(f"/api/v1/email/messages/{message_id}").status_code == 404
    approve = other.api.post(
        f"/api/v1/email/messages/{message_id}/approve",
        headers=other.csrf_headers(),
    )
    assert approve.status_code == 404, approve.text


def test_message_list_filter_by_status(session_account: Session) -> None:
    _create_draft(session_account, recipient="one@sparkcafe.in")
    two = _create_draft(session_account, recipient="two@sparkcafe.in")
    session_account.api.post(
        f"/api/v1/email/messages/{two['id']}/approve",
        headers=session_account.csrf_headers(),
    )

    drafts = session_account.api.get("/api/v1/email/messages", params={"status": "draft"})
    approved = session_account.api.get("/api/v1/email/messages", params={"status": "approved"})
    assert drafts.json()["total"] == 1
    assert approved.json()["total"] == 1
