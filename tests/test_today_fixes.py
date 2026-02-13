# tests/test_today_fixes.py
"""
Testes para as implementações de 2026-02-12:
1. Sync end_date com period.end do Stripe (invoice.paid webhook)
2. Sitemap dinâmico com páginas de criadores e grupos
3. Dashboard: link de ajuda sem target="_blank"
4. Wiki: opacidade do accordion
5. Dashboard: modal mobile CSS
"""
import os
os.environ['FLASK_ENV'] = 'testing'

import pytest
import json
import calendar
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import patch
from app import db as _db
from app.models import Creator, Group, PricingPlan, Subscription, Transaction
from app.routes.webhooks import handle_invoice_paid


def _utc_timestamp(dt):
    """Convert naive datetime (treated as UTC) to unix timestamp."""
    return calendar.timegm(dt.timetuple())


# ============================================================
# Helpers
# ============================================================

def _make_invoice(stripe_sub_id, stripe_invoice_id, billing_reason,
                  amount_cents=4990, period_end=None, period_start=None):
    """Build a minimal Stripe invoice dict for testing."""
    lines_data = []
    if period_end is not None or period_start is not None:
        lines_data = [{
            'period': {
                'start': period_start or int(datetime.utcnow().timestamp()),
                'end': period_end,
            }
        }]

    return {
        'id': stripe_invoice_id,
        'subscription': stripe_sub_id,
        'billing_reason': billing_reason,
        'amount_paid': amount_cents,
        'lines': {'data': lines_data},
        'charge': None,
        'payment_settings': {'payment_method_types': ['card']},
    }


def _setup_subscription(db, creator, group, pricing_plan, *,
                         stripe_sub_id='sub_test_123',
                         status='pending',
                         start_date=None,
                         end_date=None,
                         is_legacy=False,
                         billing_reason='subscription_create'):
    """Create a subscription + pending transaction for webhook tests."""
    sub = Subscription(
        group_id=group.id,
        plan_id=pricing_plan.id,
        telegram_user_id='555666777',
        telegram_username='webhook_user',
        stripe_subscription_id=stripe_sub_id,
        status=status,
        is_legacy=is_legacy,
        start_date=start_date or datetime.utcnow(),
        end_date=end_date or (datetime.utcnow() + timedelta(days=30)),
    )
    db.session.add(sub)
    db.session.flush()

    txn = Transaction(
        subscription_id=sub.id,
        amount=Decimal('49.90'),
        payment_method='stripe',
        status='pending',
        billing_reason=billing_reason,
    )
    db.session.add(txn)
    db.session.commit()
    return sub, txn


# ============================================================
# 1. Stripe end_date sync — subscription_create
# ============================================================

class TestInvoicePaidSubscriptionCreate:
    """handle_invoice_paid with billing_reason='subscription_create'"""

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_end_date_uses_stripe_period_end(self, mock_notify,
                                              app_context, db, creator,
                                              group, pricing_plan):
        """end_date must come from invoice.lines.data[0].period.end"""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        # Stripe says next cycle ends on Feb 13 00:00 UTC
        stripe_period_end = _utc_timestamp(datetime(2026, 2, 13, 0, 0, 0))

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_create_1',
            billing_reason='subscription_create',
            period_end=stripe_period_end,
        )

        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        assert updated.status == 'active'
        # end_date must match Stripe's period.end exactly
        expected = datetime.utcfromtimestamp(stripe_period_end)
        assert updated.end_date == expected

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_end_date_fallback_when_no_lines(self, mock_notify,
                                              app_context, db, creator,
                                              group, pricing_plan):
        """Falls back to timedelta(days=N) if Stripe lines data is empty."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_create_2',
            billing_reason='subscription_create',
        )
        # Empty lines
        invoice['lines'] = {'data': []}

        before = datetime.utcnow()
        handle_invoice_paid(invoice)
        after = datetime.utcnow()

        updated = Subscription.query.get(sub.id)
        assert updated.status == 'active'
        # Fallback: end_date ≈ now + 30 days
        expected_min = before + timedelta(days=pricing_plan.duration_days)
        expected_max = after + timedelta(days=pricing_plan.duration_days)
        assert expected_min <= updated.end_date <= expected_max

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_end_date_fallback_when_period_end_missing(self, mock_notify,
                                                        app_context, db, creator,
                                                        group, pricing_plan):
        """Falls back if period.end key is missing from lines data."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_create_3',
            billing_reason='subscription_create',
        )
        # Lines exist but no period.end
        invoice['lines'] = {'data': [{'period': {}}]}

        before = datetime.utcnow()
        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        assert updated.status == 'active'
        # Should use fallback
        assert updated.end_date >= before + timedelta(days=29)

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_31_day_month_uses_correct_date(self, mock_notify,
                                             app_context, db, creator,
                                             group, pricing_plan):
        """In a 31-day month, Stripe period.end is 31 days, not 30."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        # Jan 15 -> Feb 15 (31 days in January context)
        stripe_end = _utc_timestamp(datetime(2026, 2, 15, 0, 0, 0))

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_create_31day',
            billing_reason='subscription_create',
            period_end=stripe_end,
        )
        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        assert updated.end_date == datetime(2026, 2, 15, 0, 0, 0)

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_activates_subscription_and_credits_creator(self, mock_notify,
                                                         app_context, db, creator,
                                                         group, pricing_plan):
        """subscription_create activates sub and credits creator balance."""
        initial_balance = float(creator.balance or 0)
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        stripe_end = _utc_timestamp(datetime.utcnow() + timedelta(days=30))
        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_create_credit',
            billing_reason='subscription_create',
            period_end=stripe_end,
        )
        handle_invoice_paid(invoice)

        updated_sub = Subscription.query.get(sub.id)
        assert updated_sub.status == 'active'

        updated_creator = Creator.query.get(creator.id)
        assert float(updated_creator.balance) > initial_balance


# ============================================================
# 2. Stripe end_date sync — subscription_cycle (renewal)
# ============================================================

class TestInvoicePaidSubscriptionCycle:
    """handle_invoice_paid with billing_reason='subscription_cycle'"""

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_renewal_uses_stripe_period_end(self, mock_notify,
                                             app_context, db, creator,
                                             group, pricing_plan):
        """Renewal must use Stripe period.end for new end_date."""
        old_end = datetime(2026, 2, 13, 0, 0, 0)
        sub, txn = _setup_subscription(
            db, creator, group, pricing_plan,
            status='active',
            end_date=old_end,
            billing_reason='subscription_create',
        )

        # Stripe says next cycle ends March 13
        stripe_end = _utc_timestamp(datetime(2026, 3, 13, 0, 0, 0))

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_cycle_1',
            billing_reason='subscription_cycle',
            period_end=stripe_end,
        )
        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        assert updated.end_date == datetime(2026, 3, 13, 0, 0, 0)
        assert updated.status == 'active'

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_renewal_fallback_extends_from_end_date(self, mock_notify,
                                                      app_context, db, creator,
                                                      group, pricing_plan):
        """Without Stripe data, renewal extends from current end_date."""
        future_end = datetime.utcnow() + timedelta(days=5)
        sub, txn = _setup_subscription(
            db, creator, group, pricing_plan,
            status='active',
            end_date=future_end,
            billing_reason='subscription_create',
        )

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_cycle_fallback',
            billing_reason='subscription_cycle',
        )
        invoice['lines'] = {'data': []}

        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        # Should be old end_date + duration_days
        expected = future_end + timedelta(days=pricing_plan.duration_days)
        diff = abs((updated.end_date - expected).total_seconds())
        assert diff < 2  # within 2 seconds tolerance

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_renewal_fallback_from_now_if_already_expired(self, mock_notify,
                                                           app_context, db, creator,
                                                           group, pricing_plan):
        """If end_date already past, fallback calculates from now."""
        past_end = datetime.utcnow() - timedelta(days=2)
        sub, txn = _setup_subscription(
            db, creator, group, pricing_plan,
            status='active',
            end_date=past_end,
            billing_reason='subscription_create',
        )

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_cycle_expired',
            billing_reason='subscription_cycle',
        )
        invoice['lines'] = {'data': []}

        before = datetime.utcnow()
        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        expected_min = before + timedelta(days=pricing_plan.duration_days)
        assert updated.end_date >= expected_min

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_renewal_credits_creator(self, mock_notify,
                                      app_context, db, creator,
                                      group, pricing_plan):
        """Renewal must credit creator balance."""
        creator.balance = Decimal('100.00')
        creator.total_earned = Decimal('200.00')
        db.session.commit()

        sub, txn = _setup_subscription(
            db, creator, group, pricing_plan,
            status='active',
            billing_reason='subscription_create',
        )

        stripe_end = _utc_timestamp(datetime.utcnow() + timedelta(days=30))
        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_cycle_credit',
            billing_reason='subscription_cycle',
            amount_cents=4990,
            period_end=stripe_end,
        )
        handle_invoice_paid(invoice)

        updated_creator = Creator.query.get(creator.id)
        assert float(updated_creator.balance) > 100.00
        assert float(updated_creator.total_earned) > 200.00

    @patch('app.routes.webhooks.notify_user_via_bot')
    def test_renewal_creates_transaction(self, mock_notify,
                                          app_context, db, creator,
                                          group, pricing_plan):
        """Renewal must create a completed transaction with stripe_invoice_id."""
        sub, txn = _setup_subscription(
            db, creator, group, pricing_plan,
            status='active',
            billing_reason='subscription_create',
        )

        stripe_end = _utc_timestamp(datetime.utcnow() + timedelta(days=30))
        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_cycle_txn',
            billing_reason='subscription_cycle',
            period_end=stripe_end,
        )
        handle_invoice_paid(invoice)

        renewal_txn = Transaction.query.filter_by(
            stripe_invoice_id='in_cycle_txn'
        ).first()
        assert renewal_txn is not None
        assert renewal_txn.status == 'completed'
        assert renewal_txn.billing_reason == 'subscription_cycle'
        assert renewal_txn.paid_at is not None


# ============================================================
# 3. Idempotency — duplicate invoice protection
# ============================================================

class TestInvoicePaidIdempotency:
    """Duplicate invoice.paid events must be ignored."""

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_duplicate_invoice_skipped(self, mock_notify,
                                        app_context, db, creator,
                                        group, pricing_plan):
        """Second call with same stripe_invoice_id must be skipped."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        stripe_end = _utc_timestamp(datetime.utcnow() + timedelta(days=30))
        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_dup_test',
            billing_reason='subscription_create',
            period_end=stripe_end,
        )

        # First call
        handle_invoice_paid(invoice)
        creator_after_first = Creator.query.get(creator.id)
        balance_after_first = float(creator_after_first.balance)

        # Second call — same invoice
        handle_invoice_paid(invoice)
        creator_after_second = Creator.query.get(creator.id)
        balance_after_second = float(creator_after_second.balance)

        # Balance must not change on duplicate
        assert balance_after_second == balance_after_first

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_different_invoices_both_processed(self, mock_notify,
                                                app_context, db, creator,
                                                group, pricing_plan):
        """Different invoice IDs for same subscription must both process."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        stripe_end_1 = _utc_timestamp(datetime(2026, 2, 13))
        stripe_end_2 = _utc_timestamp(datetime(2026, 3, 13))

        invoice1 = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_first',
            billing_reason='subscription_create',
            period_end=stripe_end_1,
        )
        handle_invoice_paid(invoice1)

        invoice2 = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_second',
            billing_reason='subscription_cycle',
            period_end=stripe_end_2,
        )
        handle_invoice_paid(invoice2)

        updated = Subscription.query.get(sub.id)
        assert updated.end_date == datetime(2026, 3, 13)

        txn_count = Transaction.query.filter_by(
            subscription_id=sub.id, status='completed'
        ).count()
        assert txn_count >= 2


# ============================================================
# 4. handle_invoice_paid — edge cases and security
# ============================================================

class TestInvoicePaidEdgeCases:
    """Edge cases and safety nets for handle_invoice_paid."""

    def test_no_subscription_id_skipped(self, app_context, db):
        """Invoice without subscription ID should be skipped."""
        invoice = _make_invoice(
            stripe_sub_id=None,
            stripe_invoice_id='in_nosub',
            billing_reason='subscription_create',
        )
        # Should not raise
        handle_invoice_paid(invoice)

    def test_unknown_subscription_skipped(self, app_context, db):
        """Invoice for unknown stripe_subscription_id should be skipped."""
        invoice = _make_invoice(
            stripe_sub_id='sub_nonexistent_999',
            stripe_invoice_id='in_unknown',
            billing_reason='subscription_create',
        )
        handle_invoice_paid(invoice)

    def test_unhandled_billing_reason(self, app_context, db, creator,
                                      group, pricing_plan):
        """Unhandled billing_reason should not crash."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_manual',
            billing_reason='manual',
        )
        # Should not raise
        handle_invoice_paid(invoice)

    @patch('app.routes.webhooks.notify_bot_payment_complete')
    def test_period_end_zero_treated_as_falsy(self, mock_notify,
                                               app_context, db, creator,
                                               group, pricing_plan):
        """period.end = 0 should trigger fallback (epoch 0 is invalid)."""
        sub, txn = _setup_subscription(db, creator, group, pricing_plan)

        invoice = _make_invoice(
            stripe_sub_id='sub_test_123',
            stripe_invoice_id='in_zero_period',
            billing_reason='subscription_create',
            period_end=0,
        )

        handle_invoice_paid(invoice)

        updated = Subscription.query.get(sub.id)
        # period_end=0 is falsy, so fallback should be used
        # end_date should be roughly now + duration_days, not epoch 0
        assert updated.end_date > datetime(2026, 1, 1)


# ============================================================
# 5. Dynamic Sitemap
# ============================================================

class TestDynamicSitemap:
    """Tests for the dynamic sitemap route."""

    def test_sitemap_returns_xml(self, client):
        """Sitemap should return valid XML with correct content type."""
        resp = client.get('/sitemap.xml')
        assert resp.status_code == 200
        assert resp.content_type == 'application/xml'
        assert b'<?xml version="1.0"' in resp.data
        assert b'<urlset' in resp.data
        assert b'</urlset>' in resp.data

    def test_sitemap_contains_static_pages(self, client):
        """Sitemap must include all static pages."""
        resp = client.get('/sitemap.xml')
        data = resp.data.decode()

        static_paths = ['/', '/recursos', '/precos', '/como-funciona',
                        '/termos', '/privacidade', '/denuncia']
        for path in static_paths:
            assert f'televip.app{path}</loc>' in data

    def test_sitemap_contains_creator_page(self, client, creator):
        """Active creator page should appear in sitemap."""
        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert f'/c/{creator.username}</loc>' in data

    def test_sitemap_contains_public_group(self, client, creator, group):
        """Public active group should appear in sitemap."""
        group.is_public = True
        _db.session.commit()

        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert f'/c/{creator.username}/{group.invite_slug}</loc>' in data

    def test_sitemap_excludes_private_group(self, client, creator, group):
        """Private group should NOT appear in sitemap."""
        group.is_public = False
        _db.session.commit()

        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert group.invite_slug not in data

    def test_sitemap_excludes_inactive_group(self, client, creator, group):
        """Inactive group should NOT appear in sitemap."""
        group.is_public = True
        group.is_active = False
        _db.session.commit()

        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert group.invite_slug not in data

    def test_sitemap_excludes_blocked_creator(self, client, db):
        """Blocked creator should NOT appear in sitemap."""
        blocked = Creator(
            name='Blocked', email='blocked@test.com',
            username='blockeduser', is_blocked=True, is_verified=True,
        )
        blocked.set_password('Pass1234')
        db.session.add(blocked)
        db.session.commit()

        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert 'blockeduser' not in data

    def test_sitemap_excludes_inactive_creator(self, client, db):
        """Inactive creator should NOT appear in sitemap."""
        inactive = Creator(
            name='Inactive', email='inactive@test.com',
            username='inactiveuser', is_active=False, is_verified=True,
        )
        inactive.set_password('Pass1234')
        db.session.add(inactive)
        db.session.commit()

        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert 'inactiveuser' not in data

    def test_sitemap_has_changefreq_and_priority(self, client):
        """Sitemap entries should include changefreq and priority."""
        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert '<changefreq>' in data
        assert '<priority>' in data

    def test_sitemap_multiple_creators(self, client, creator, second_creator):
        """Multiple active creators should all appear."""
        resp = client.get('/sitemap.xml')
        data = resp.data.decode()
        assert f'/c/{creator.username}</loc>' in data
        assert f'/c/{second_creator.username}</loc>' in data


# ============================================================
# 6. Robots.txt
# ============================================================

class TestRobotsTxt:
    """Robots.txt must reference the sitemap."""

    def test_robots_contains_sitemap(self, client):
        resp = client.get('/robots.txt')
        assert resp.status_code == 200
        assert b'Sitemap: https://televip.app/sitemap.xml' in resp.data


# ============================================================
# 7. Dashboard template checks
# ============================================================

class TestDashboardTemplate:
    """Verify template changes: help link and modal CSS."""

    def test_help_link_no_target_blank(self):
        """Help link should NOT have target='_blank' (iOS Safari issue)."""
        import os
        import re
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'app', 'templates',
            'dashboard', 'index.html'
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            data = f.read()

        # Find the wiki/Ajuda qa-tile link — must NOT have target="_blank"
        wiki_links = re.findall(r'<a[^>]*wiki[^>]*qa-tile[^>]*>', data)
        wiki_links += re.findall(r'<a[^>]*qa-tile[^>]*wiki[^>]*>', data)
        assert len(wiki_links) > 0, "Wiki qa-tile link not found in template"
        for link in wiki_links:
            assert 'target=' not in link, \
                f"Help link still has target attribute: {link}"


# ============================================================
# 8. Wiki accordion opacity
# ============================================================

class TestWikiAccordion:
    """Wiki page accordion background opacity."""

    def test_accordion_has_dark_background(self, client):
        """Accordion items should have opaque dark background."""
        resp = client.get('/como-funciona')
        assert resp.status_code == 200
        data = resp.data.decode()
        # Should have the darker rgba value, not the original 0.05
        assert 'rgba(11, 14, 26, 0.92)' in data
        assert 'rgba(255, 255, 255, 0.05)' not in data or \
               '.wiki-accordion' not in data.split('rgba(255, 255, 255, 0.05)')[0][-200:]


# ============================================================
# 9. Mobile modal CSS
# ============================================================

class TestMobileModalCSS:
    """Dashboard CSS must include mobile modal fix."""

    def test_modal_mobile_css_present(self, client, creator):
        """dashboard.css must contain mobile modal centering rules."""
        resp = client.get('/static/css/dashboard.css')
        assert resp.status_code == 200
        data = resp.data.decode()

        # Must have mobile modal fix
        assert 'max-height: calc(100dvh - 1rem)' in data
        assert 'overflow-y: auto' in data
