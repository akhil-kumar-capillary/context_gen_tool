"""Comprehensive tests for CapillaryAPIClient — all 89 methods, auth validation.

Tests validate:
1. Every method hits the correct URL path with the correct HTTP method
2. Every method uses the correct auth type (Bearer vs Cookie)
3. Cookie-auth requests never contain Authorization header (the original HTTP 520 bug)
4. Bearer-auth requests never contain Cookie header
5. Error handling (HTTP errors, API-level errors, timeouts)
6. Sequential calls between auth types don't leak headers
"""

import json

import httpx
import pytest
import respx

from app.services.config_apis.client import (
    APIError,
    BaseAPIClient,
    CapillaryAPIClient,
    _BROWSER_UA,
    _COOKIE_AUTH_MARKERS,
    SERVICE_PATHS,
)

# ---------------------------------------------------------------------------
# Test constants (must match conftest.py)
# ---------------------------------------------------------------------------
TEST_HOST = "test.example.com"
TEST_TOKEN = "test-token-abc123"
TEST_ORG_ID = 100
BASE_URL = f"https://{TEST_HOST}"

# Standard mock responses
OK_JSON = {"success": True, "data": []}
OK_ITEMS = {"success": True, "data": [{"id": 1, "name": "test"}]}
OK_BINARY = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Auth assertion helpers
# ---------------------------------------------------------------------------


def assert_bearer_auth(request: httpx.Request) -> None:
    """Assert request uses Bearer token auth (no Cookie)."""
    auth = request.headers.get("authorization")
    assert auth == f"Bearer {TEST_TOKEN}", (
        f"Expected 'Bearer {TEST_TOKEN}', got '{auth}'"
    )
    assert "cookie" not in request.headers, (
        f"Bearer request must NOT have Cookie, got: {request.headers.get('cookie')}"
    )


def assert_cookie_auth(request: httpx.Request) -> None:
    """Assert request uses Cookie auth (no Authorization)."""
    cookie = request.headers.get("cookie")
    assert cookie is not None, "Cookie-auth request must have Cookie header"
    assert f"CT={TEST_TOKEN}" in cookie, f"Cookie missing CT token: {cookie}"
    assert f"OID={TEST_ORG_ID}" in cookie, f"Cookie missing OID: {cookie}"
    assert "authorization" not in request.headers, (
        f"Cookie request must NOT have Authorization, "
        f"got: {request.headers.get('authorization')}"
    )
    # httpx merges per-request User-Agent with client default, so check containment
    assert _BROWSER_UA in request.headers.get("user-agent", "")
    assert request.headers.get("x-cap-org") == str(TEST_ORG_ID)
    assert "x-cap-request-id" in request.headers


# =========================================================================
# A. BaseAPIClient unit tests
# =========================================================================


class TestBaseAPIClient:
    """Low-level tests for BaseAPIClient auth logic."""

    async def test_default_headers_no_auth(self):
        """_default_headers must NOT contain auth — auth is per-request only."""
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            defaults = dict(c._http.headers)
            assert "authorization" not in {k.lower() for k in defaults}
            assert "x-cap-api-auth-org-id" not in {k.lower() for k in defaults}
            assert defaults.get("accept") == "application/json"

    async def test_prepare_headers_bearer_path(self):
        """Non-cookie path should get Bearer + org_id, no Cookie."""
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            h = c._prepare_headers("/loyalty/api/v1/programs")
            assert h["Authorization"] == f"Bearer {TEST_TOKEN}"
            assert h["X-CAP-API-AUTH-ORG-ID"] == str(TEST_ORG_ID)
            assert "Cookie" not in h

    async def test_prepare_headers_cookie_path(self):
        """Cookie-auth path should get Cookie, no Authorization."""
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            h = c._prepare_headers("/iris/v2/audience")
            assert f"CT={TEST_TOKEN}" in h["Cookie"]
            assert f"OID={TEST_ORG_ID}" in h["Cookie"]
            assert "Authorization" not in h
            assert h["User-Agent"] == _BROWSER_UA
            assert h["X-CAP-ORG"] == str(TEST_ORG_ID)
            assert "X-CAP-REQUEST-ID" in h

    async def test_prepare_headers_cookie_uses_caller_bearer_token(self):
        """If caller passes Authorization header, it should be extracted for Cookie."""
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            h = c._prepare_headers(
                "/iris/v2/test",
                headers={"Authorization": "Bearer custom-tok"},
            )
            assert "CT=custom-tok" in h["Cookie"]
            assert "Authorization" not in h

    async def test_prepare_headers_cookie_missing_org_raises(self):
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, org_id=None) as c:
            with pytest.raises(APIError, match="org_id is required"):
                c._prepare_headers("/iris/v2/test")

    async def test_prepare_headers_cookie_missing_token_raises(self):
        async with CapillaryAPIClient(TEST_HOST, token=None, org_id=TEST_ORG_ID) as c:
            with pytest.raises(APIError, match="token is required"):
                c._prepare_headers("/iris/v2/test")

    @pytest.mark.parametrize("marker", _COOKIE_AUTH_MARKERS)
    async def test_needs_cookie_auth_markers(self, marker):
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            assert c._needs_cookie_auth(f"/some{marker}path") is True

    async def test_needs_cookie_auth_non_marker(self):
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            assert c._needs_cookie_auth("/loyalty/api/v1/programs") is False

    async def test_check_api_response_success_false(self):
        with pytest.raises(APIError, match="success=False"):
            BaseAPIClient._check_api_response(
                {"success": False, "message": "bad"}, 200
            )

    async def test_check_api_response_nested_status_error(self):
        with pytest.raises(APIError) as exc_info:
            BaseAPIClient._check_api_response(
                {"status": {"code": 401, "message": "unauthorized"}}, 200
            )
        assert exc_info.value.status_code == 401

    async def test_check_api_response_ok(self):
        # Should not raise
        BaseAPIClient._check_api_response({"success": True, "data": []}, 200)
        BaseAPIClient._check_api_response({"status": {"code": 200}}, 200)

    async def test_context_manager(self):
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, TEST_ORG_ID) as c:
            assert not c._http.is_closed
        assert c._http.is_closed


# =========================================================================
# B. CouponAPI — 7 methods, all Bearer
# =========================================================================


class TestCouponAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_list_coupon_series(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/config").respond(200, json=OK_JSON)
        result = await api_client.coupon.list_coupon_series()
        assert result == OK_JSON
        assert_bearer_auth(respx_mock.calls[0].request)
        assert "ownedBy=NONE" in str(respx_mock.calls[0].request.url)

    @respx.mock(base_url=BASE_URL)
    async def test_list_coupon_series_with_params(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/config").respond(200, json=OK_JSON)
        await api_client.coupon.list_coupon_series(
            program_id=5, owned_by="LOYALTY", include_unclaimed=True
        )
        url = str(respx_mock.calls[0].request.url)
        assert "ownerId=5" in url
        assert "ownedBy=LOYALTY" in url
        assert "includeUnclaimed=true" in url

    @respx.mock(base_url=BASE_URL)
    async def test_get_coupon_series_by_id(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/config/42").respond(200, json=OK_JSON)
        await api_client.coupon.get_coupon_series_by_id(42)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_custom_property(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/customProperty").respond(200, json=OK_JSON)
        await api_client.coupon.get_custom_property()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_org_settings(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/orgSettings").respond(200, json=OK_JSON)
        await api_client.coupon.get_org_settings()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_product_categories(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/entity/product/categories").respond(200, json=OK_JSON)
        await api_client.coupon.get_product_categories()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_product_brands(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/entity/product/brands").respond(200, json=OK_JSON)
        await api_client.coupon.get_product_brands()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_product_attributes(self, api_client, respx_mock):
        respx_mock.get("/coupon/api/v1/entity/product/attributes").respond(200, json=OK_JSON)
        await api_client.coupon.get_product_attributes()
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# C. LoyaltyAPI — 19 methods, all Bearer
# =========================================================================


class TestLoyaltyAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_loyalty_programs(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(200, json=OK_JSON)
        await api_client.loyalty.get_loyalty_programs()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_loyalty_program_by_id(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_loyalty_program_by_id(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_all_partner_programs_by_lp_id(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs/partner-programs/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_all_partner_programs_by_lp_id(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_all_tiers_by_lp_id(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs/tiers/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_all_tiers_by_lp_id(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_strategies(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/strategy/points/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_strategies(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_liability_owners(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/liability/liabilityOwners").respond(200, json=OK_JSON)
        await api_client.loyalty.get_liability_owners()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_custom_fields(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/settings/custom-field").respond(200, json=OK_JSON)
        await api_client.loyalty.get_custom_fields()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_ruleset_scoping(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/workflows/rulesets-scoping/scope").respond(200, json=OK_JSON)
        await api_client.loyalty.get_ruleset_scoping("CustomerCluster")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "type=CustomerCluster" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_org_labels(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/workflows/org-labels").respond(200, json=OK_JSON)
        await api_client.loyalty.get_org_labels()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_event_types(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/workflows/event-types/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_event_types(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_list_promotions(self, api_client, respx_mock):
        respx_mock.get("/loyalty/emf/v1/programs/promotions/list").respond(200, json=OK_JSON)
        await api_client.loyalty.list_promotions(limit=10, offset=0)
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "limit=10" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_promotion(self, api_client, respx_mock):
        respx_mock.get("/loyalty/emf/v1/programs/1/promotions/2/get").respond(200, json=OK_JSON)
        await api_client.loyalty.get_promotion(promotion_id=2, program_id=1)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_liability_split(self, api_client, respx_mock):
        respx_mock.get(
            "/loyalty/api/v1/liability/liabilityOwnersForComponent/PROMOTION/7"
        ).respond(200, json=OK_JSON)
        await api_client.loyalty.get_liability_split(7)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_line_item_extended_fields(self, api_client, respx_mock):
        respx_mock.get(
            "/loyalty/api/v1/trackers/extendedFields/5/LINEITEM_EXTENDED_FIELD"
        ).respond(200, json=OK_JSON)
        await api_client.loyalty.get_line_item_extended_fields(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_txn_extended_fields(self, api_client, respx_mock):
        respx_mock.get(
            "/loyalty/api/v1/trackers/extendedFields/5/BILL_EXTENDED_FIELD"
        ).respond(200, json=OK_JSON)
        await api_client.loyalty.get_txn_extended_fields(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_customer_extended_fields(self, api_client, respx_mock):
        respx_mock.get(
            "/loyalty/api/v1/trackers/extendedFields/5/CUSTOMER_EXTENDED_FIELD"
        ).respond(200, json=OK_JSON)
        await api_client.loyalty.get_customer_extended_fields(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_alternate_currencies(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/alternateCurrency/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_alternate_currencies(5)
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "pageSize=1000" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_subscription_partner_programs(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/partner-program/5").respond(200, json=OK_JSON)
        await api_client.loyalty.get_subscription_partner_programs(5)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_tender_combination_types(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/strategy/tender-combination/types/5").respond(
            200, json=OK_JSON
        )
        await api_client.loyalty.get_tender_combination_types(5)
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# D. CampaignAPI — 24 methods, MIXED auth (13 cookie, 11 bearer)
# =========================================================================


class TestCampaignAPI:
    """Most critical service — mixes IRIS (cookie), ADIONA (cookie), CREATIVES (bearer)."""

    # --- Cookie-auth (IRIS paths) ---

    @respx.mock(base_url=BASE_URL)
    async def test_get_audiences(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/audience").respond(200, json=OK_JSON)
        await api_client.campaigns.get_audiences()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_audience_by_id(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/audience/abc").respond(200, json=OK_JSON)
        await api_client.campaigns.get_audience_by_id("abc")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_list_campaigns(self, api_client, respx_mock):
        respx_mock.post("/iris/v2/campaigns/filter").respond(200, json=OK_JSON)
        await api_client.campaigns.list_campaigns()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_campaign_by_id(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/campaigns/1").respond(200, json=OK_JSON)
        await api_client.campaigns.get_campaign_by_id(1)
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_default_attribution(self, api_client, respx_mock):
        """ADIONA path → cookie auth."""
        respx_mock.get("/adiona/api/v1/attribution/default").respond(200, json=OK_JSON)
        await api_client.campaigns.get_default_attribution()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_referral_and_survey(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/campaigns/type").respond(200, json=OK_JSON)
        await api_client.campaigns.get_referral_and_survey()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_domain_properties(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/org/campaign/meta/domainProperties").respond(200, json=OK_JSON)
        await api_client.campaigns.get_domain_properties("SMS")
        req = respx_mock.calls[0].request
        assert_cookie_auth(req)
        assert "channel=SMS" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_brand_point_of_contact(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/audience").respond(200, json=OK_JSON)
        await api_client.campaigns.get_brand_point_of_contact()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_program_configurations(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/org/campaign/meta/loyaltyProgram").respond(200, json=OK_JSON)
        await api_client.campaigns.get_program_configurations()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_list_campaign_messages(self, api_client, respx_mock):
        respx_mock.post("/iris/v2/campaigns/1/messages/filter").respond(200, json=OK_JSON)
        await api_client.campaigns.list_campaign_messages(1)
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_campaign_message_by_id(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/campaigns/1/messages/msg1").respond(200, json=OK_JSON)
        await api_client.campaigns.get_campaign_message_by_id(1, "msg1")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_check_message_name_already_exists(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/campaigns/1/messages/checkExists").respond(200, json=OK_JSON)
        await api_client.campaigns.check_message_name_already_exists(1, "test")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_check_campaign_name_already_exists(self, api_client, respx_mock):
        respx_mock.get("/iris/v2/campaigns/checkExists").respond(200, json=OK_JSON)
        await api_client.campaigns.check_campaign_name_already_exists("test")
        assert_cookie_auth(respx_mock.calls[0].request)

    # --- Bearer-auth (CREATIVES paths — no cookie marker match) ---

    @respx.mock(base_url=BASE_URL)
    async def test_get_sms_templates(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/Sms").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_sms_templates()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_email_templates(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/Email").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_email_templates()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_whatsapp_accounts(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/meta/wecrm").respond(200, json=OK_JSON)
        await api_client.campaigns.get_whatsapp_accounts()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_whatsapp_templates(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/WhatsApp").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_whatsapp_templates("acc1", "host.com")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_push_notification_accounts(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/meta/wecrm").respond(200, json=OK_JSON)
        await api_client.campaigns.get_push_notification_accounts()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_push_notification_templates(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/MobilePush").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_push_notification_templates("acc1")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_sms_template_by_id(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/tmpl1/SMS").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_sms_template_by_id("tmpl1")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_email_template_by_id(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/tmpl1/EMAIL").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_email_template_by_id("tmpl1")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_push_notification_template_by_id(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/tmpl1/SMS").respond(
            200, json=OK_JSON
        )
        await api_client.campaigns.get_push_notification_template_by_id("tmpl1")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_central_communication_by_meta_ids(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/creatives/creatives/common/central-comms/meta-id/TRANSACTION"
        ).respond(200, json=OK_JSON)
        await api_client.campaigns.get_central_communication_by_meta_ids(["m1", "m2"])
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_email_template_content(self, api_client, respx_mock):
        """template_url is a CREATIVES path → bearer auth."""
        path = "/arya/api/v1/creatives/creatives/templates/v1/content/tmpl1"
        respx_mock.get(path).respond(200, json={"text": "<html>Hello</html>"})
        result = await api_client.campaigns.get_email_template_content(path)
        assert result == "<html>Hello</html>"
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# E. PromotionAPI — 11 methods, 10 bearer + 1 cookie (segments)
# =========================================================================


class TestPromotionAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_cart_promo_by_id(self, api_client, respx_mock):
        respx_mock.get("/v1/promotion-management/promotions/promo1").respond(200, json=OK_JSON)
        await api_client.promotion.get_cart_promo_or_gift_voucher_by_id("promo1")
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_cart_promo_by_name(self, api_client, respx_mock):
        respx_mock.get("/v1/promotion-management/promotions/filters").respond(200, json=OK_JSON)
        await api_client.promotion.get_cart_promo_or_gift_voucher_by_name(active=True)
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "active=true" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_vendors_list(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/vendors/list/brand/1").respond(200, json=OK_JSON)
        await api_client.promotion.get_vendors_list(1)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_vendor_redemptions_list_by_type(self, api_client, respx_mock):
        """Branch: redemption_type only (no brand_id, no vendor_redemption_id)."""
        respx_mock.get("/incentives/api/v1/rewards/vendors/vendor/redemption/list").respond(
            200, json=OK_JSON
        )
        await api_client.promotion.get_vendor_redemptions_list(redemption_type="VOUCHER")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "redemptionType=VOUCHER" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_vendor_redemptions_list_by_ids(self, api_client, respx_mock):
        """Branch: all IDs provided."""
        respx_mock.get(
            "/incentives/api/v1/rewards/vendors/vendor/10/redemption/20/brand/30"
        ).respond(200, json=OK_JSON)
        await api_client.promotion.get_vendor_redemptions_list(
            brand_id=30, vendor_id=10, vendor_redemption_id=20
        )
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_segments_list_cookie(self, api_client, respx_mock):
        """get_segments_list uses NSE path → cookie auth. Boundary test!"""
        respx_mock.get("/arya/api/v1/nse/nse/segmentation-api/v2/segments").respond(
            200, json=OK_JSON
        )
        await api_client.promotion.get_segments_list()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_categories_list(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/settings/category/brand/1").respond(
            200, json=OK_JSON
        )
        await api_client.promotion.get_categories_list(1)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_languages_list(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/settings/languages").respond(200, json=OK_JSON)
        await api_client.promotion.get_languages_list()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_groups_list(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/settings/groups").respond(200, json=OK_JSON)
        await api_client.promotion.get_groups_list()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_custom_fields_list(self, api_client, respx_mock):
        respx_mock.get(
            "/incentives/api/v1/rewards/settings/custom-fields/unified-cf-rc"
        ).respond(200, json=OK_JSON)
        await api_client.promotion.get_custom_fields_list()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_reward_response_by_id(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/reward/5/brand/1").respond(200, json=OK_JSON)
        await api_client.promotion.get_reward_response_by_id(5, 1)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_rewards_list(self, api_client, respx_mock):
        respx_mock.get("/incentives/api/v1/rewards/list/brand/1").respond(200, json=OK_JSON)
        await api_client.promotion.get_rewards_list(1, "test")
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# F. RewardAPI — 4 methods, all Cookie (/core/v1/)
# =========================================================================


class TestRewardAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_list_catalog_rewards(self, api_client, respx_mock):
        respx_mock.get("/core/v1/reward/brand/5").respond(200, json=OK_JSON)
        await api_client.reward.list_catalog_rewards(5)
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_brands(self, api_client, respx_mock):
        respx_mock.post("/core/v1/brand/getAll").respond(200, json=OK_JSON)
        await api_client.reward.get_brands()
        req = respx_mock.calls[0].request
        assert_cookie_auth(req)
        body = json.loads(req.content)
        assert body == {"orgIds": [TEST_ORG_ID]}

    @respx.mock(base_url=BASE_URL)
    async def test_get_fulfillment_status(self, api_client, respx_mock):
        respx_mock.get("/core/v1/fulfillmentStatus").respond(200, json=OK_JSON)
        await api_client.reward.get_fulfillment_status()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_custom_fields(self, api_client, respx_mock):
        respx_mock.get("/core/v1/brand/customfield").respond(200, json=OK_JSON)
        await api_client.reward.get_custom_fields()
        assert_cookie_auth(respx_mock.calls[0].request)


# =========================================================================
# G. OrgSettingsAPI — 6 methods, all Bearer
# =========================================================================


class TestOrgSettingsAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_till_details(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/org-settings/target-groups/till-credentials").respond(
            200, json=OK_JSON
        )
        await api_client.org_settings.get_till_details("TILL001")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "code=TILL001" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_all_target_groups(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/org-settings/target-groups/targets").respond(
            200, json=OK_JSON
        )
        await api_client.org_settings.get_all_target_groups()
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "limit=10000" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_tg_by_id(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/org-settings/target-groups/targetGroup/7").respond(
            200, json=OK_JSON
        )
        await api_client.org_settings.get_tg_by_id(7)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_periods_for_target_group(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/org-settings/target-groups/targetGroups/targetPeriods/7"
        ).respond(200, json=OK_JSON)
        await api_client.org_settings.get_periods_for_target_group(7)
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_behavioral_events(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/org-settings/events/list").respond(200, json=OK_JSON)
        await api_client.org_settings.get_behavioral_events()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_customer_labels(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/org-settings/customer-status-configuration/labels"
        ).respond(200, json=OK_JSON)
        await api_client.org_settings.get_customer_labels()
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# H. CartPromotionAPI — 2 methods, all Bearer
# =========================================================================


class TestCartPromotionAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_custom_fields_for_cart_promotion(self, api_client, respx_mock):
        respx_mock.get("/v1/promotion-management/promotions/settings/custom_field").respond(
            200, json=OK_JSON
        )
        await api_client.cart_promotion.get_custom_fields_for_cart_promotion()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_cart_promotion_features_by_id(self, api_client, respx_mock):
        respx_mock.get("/v1/promotion-management/promotions/promo1/SCOPE").respond(
            200, json=OK_JSON
        )
        await api_client.cart_promotion.get_cart_promotion_features_by_id("promo1", "SCOPE")
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# I. IntouchAPI — 1 method, Bearer
# =========================================================================


class TestIntouchAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_organization_hierarchy(self, api_client, respx_mock):
        respx_mock.get("/v2/organization/hierarchy").respond(200, json=OK_JSON)
        await api_client.intouch.get_organization_hierarchy()
        assert_bearer_auth(respx_mock.calls[0].request)


# =========================================================================
# J. AryaAPI — 3 methods, mixed (2 bearer, 1 cookie via /nse/)
# =========================================================================


class TestAryaAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_entities(self, api_client, respx_mock):
        respx_mock.get(f"/arya/api/v1/org/{TEST_ORG_ID}/entities").respond(200, json=OK_JSON)
        await api_client.arya.get_entities("STORE")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "type=STORE" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_get_org_list(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/org/list").respond(200, json=OK_JSON)
        await api_client.arya.get_org_list()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_customers_count_cookie(self, api_client, respx_mock):
        """NSE path → cookie auth. Boundary test for AryaAPI."""
        respx_mock.get("/arya/api/v1/nfs/filters/customers").respond(200, json=OK_JSON)
        await api_client.arya.get_customers_count()
        assert_cookie_auth(respx_mock.calls[0].request)

    async def test_get_entities_no_org_id_raises(self):
        async with CapillaryAPIClient(TEST_HOST, TEST_TOKEN, org_id=None) as c:
            with pytest.raises(APIError, match="org_id is required"):
                await c.arya.get_entities("STORE")


# =========================================================================
# K. FTPAPI — 1 method, Bearer with custom headers
# =========================================================================


class TestFTPAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_ftp_credentials(self, api_client, respx_mock):
        respx_mock.get(f"/reonexport/v1/orgs/{TEST_ORG_ID}/ftp/tag1/").respond(200, json=OK_JSON)
        await api_client.ftp.get_ftp_credentials(TEST_ORG_ID, "tag1")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert req.headers["x-cap-api-auth-user-id"] == "-1"
        assert req.headers["x-cap-api-auth-module"] == "export"
        assert req.headers["x-cap-request-id"] == "ftp-export-request"


# =========================================================================
# L. AudienceAPI — 6 methods, all Cookie (/nse/)
# =========================================================================


class TestAudienceAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_dim_attr_values(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/nfs/meta/getdimensionattrvalues/store/city"
        ).respond(200, json=OK_JSON)
        await api_client.audience.get_dim_attr_values("store", "city")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_search_dim_attr_values(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/nfs/meta/searchdimensionattrvalues/store/city/new/true"
        ).respond(200, json=OK_JSON)
        await api_client.audience.search_dim_attr_values("store", "city", "new")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_hierarchy_data_via_dimension(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/nfs/meta/getmultidimensions/store").respond(
            200, json=OK_JSON
        )
        await api_client.audience.get_hierarchy_data_via_dimension("store")
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_dim_attr_value_availability(self, api_client, respx_mock):
        respx_mock.get(
            "/arya/api/v1/nfs/meta/getdimattrvalueavailability"
        ).respond(200, json=OK_JSON)
        await api_client.audience.get_dim_attr_value_availability()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_audience_filters(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/nfs/filters/").respond(200, json=OK_JSON)
        await api_client.audience.get_audience_filters()
        assert_cookie_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_customer_test_control(self, api_client, respx_mock):
        respx_mock.get("/arya/api/v1/nfs/filters/customers").respond(200, json=OK_JSON)
        await api_client.audience.get_customer_test_control()
        req = respx_mock.calls[0].request
        assert_cookie_auth(req)
        assert "context=campaign" in str(req.url)


# =========================================================================
# M. MySQLAPI — 1 method, Bearer
# =========================================================================


class TestMySQLAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_events(self, api_client, respx_mock):
        respx_mock.get("/ask-aira/copilot/mysql/events/promotions").respond(200, json=OK_JSON)
        await api_client.mysql.get_events("promotions", start_date="2024-01-01", limit=10)
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "start_date=2024-01-01" in str(req.url)
        assert "limit=10" in str(req.url)


# =========================================================================
# N. RAGAPI — 4 methods (3 bearer, 1 binary with no auth)
# =========================================================================


class TestRAGAPI:
    @respx.mock(base_url=BASE_URL)
    async def test_get_contexts(self, api_client, respx_mock):
        respx_mock.get("/ask-aira/copilot/get_contexts").respond(200, json=OK_JSON)
        await api_client.rag.get_contexts()
        assert_bearer_auth(respx_mock.calls[0].request)

    @respx.mock(base_url=BASE_URL)
    async def test_get_context_attachment_file_no_auth(self, api_client, respx_mock):
        """_get_binary does NOT call _prepare_headers → no auth headers.
        This is a known limitation (potential latent bug if endpoint needs auth)."""
        respx_mock.get("/ask-aira/copilot/get_context_attachment_file").respond(
            200, content=OK_BINARY
        )
        result = await api_client.rag.get_context_attachment_file("ctx1", "file.txt")
        assert result == OK_BINARY
        req = respx_mock.calls[0].request
        assert "authorization" not in req.headers
        assert "cookie" not in req.headers

    @respx.mock(base_url=BASE_URL)
    async def test_get_inference_view(self, api_client, respx_mock):
        respx_mock.get("/ask-aira/copilot/get_inference_view").respond(200, json=OK_JSON)
        await api_client.rag.get_inference_view("inf-123")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "inference_id=inf-123" in str(req.url)

    @respx.mock(base_url=BASE_URL)
    async def test_download_org_payloads(self, api_client, respx_mock):
        respx_mock.get("/ask-aira/copilot/download_org_payloads").respond(200, json=OK_JSON)
        await api_client.rag.download_org_payloads("org1", "v2")
        req = respx_mock.calls[0].request
        assert_bearer_auth(req)
        assert "org_id=org1" in str(req.url)


# =========================================================================
# O. Error Handling
# =========================================================================


class TestErrorHandling:
    @respx.mock(base_url=BASE_URL)
    async def test_http_404_raises(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(404, text="Not Found")
        with pytest.raises(APIError, match="HTTP 404") as exc_info:
            await api_client.loyalty.get_loyalty_programs()
        assert exc_info.value.status_code == 404

    @respx.mock(base_url=BASE_URL)
    async def test_http_520_raises(self, api_client, respx_mock):
        """520 is the exact error from the original cookie-auth bug."""
        respx_mock.get("/iris/v2/audience").respond(520, text="Origin Error")
        with pytest.raises(APIError, match="HTTP 520"):
            await api_client.campaigns.get_audiences()

    @respx.mock(base_url=BASE_URL)
    async def test_success_false_raises(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(
            200, json={"success": False, "message": "Invalid token"}
        )
        with pytest.raises(APIError, match="success=False"):
            await api_client.loyalty.get_loyalty_programs()

    @respx.mock(base_url=BASE_URL)
    async def test_nested_status_error(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(
            200, json={"status": {"code": 401, "message": "Unauthorized"}}
        )
        with pytest.raises(APIError) as exc_info:
            await api_client.loyalty.get_loyalty_programs()
        assert exc_info.value.status_code == 401

    @respx.mock(base_url=BASE_URL)
    async def test_non_json_response(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(
            200, text="plain text", headers={"content-type": "text/plain"}
        )
        result = await api_client.loyalty.get_loyalty_programs()
        assert result == {"text": "plain text"}

    @respx.mock(base_url=BASE_URL)
    async def test_post_500_raises(self, api_client, respx_mock):
        respx_mock.post("/iris/v2/campaigns/filter").respond(500, text="Internal Error")
        with pytest.raises(APIError, match="HTTP 500"):
            await api_client.campaigns.list_campaigns()

    @respx.mock(base_url=BASE_URL)
    async def test_timeout_raises(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").mock(
            side_effect=httpx.ConnectTimeout("Connection timed out")
        )
        with pytest.raises(APIError, match="Request failed"):
            await api_client.loyalty.get_loyalty_programs()

    @respx.mock(base_url=BASE_URL)
    async def test_binary_403_raises(self, api_client, respx_mock):
        respx_mock.get("/ask-aira/copilot/get_context_attachment_file").respond(
            403, text="Forbidden"
        )
        with pytest.raises(APIError, match="HTTP 403"):
            await api_client.rag.get_context_attachment_file("ctx1", "f.txt")


# =========================================================================
# P. Auth Isolation (regression tests for the HTTP 520 bug)
# =========================================================================


class TestAuthIsolation:
    """Verify sequential calls with different auth types don't leak headers."""

    @respx.mock(base_url=BASE_URL)
    async def test_bearer_then_cookie_then_bearer(self, api_client, respx_mock):
        respx_mock.get("/loyalty/api/v1/programs").respond(200, json=OK_JSON)
        respx_mock.get("/iris/v2/audience").respond(200, json=OK_JSON)
        respx_mock.get("/coupon/api/v1/config").respond(200, json=OK_JSON)

        await api_client.loyalty.get_loyalty_programs()
        assert_bearer_auth(respx_mock.calls[0].request)

        await api_client.campaigns.get_audiences()
        assert_cookie_auth(respx_mock.calls[1].request)

        await api_client.coupon.list_coupon_series()
        assert_bearer_auth(respx_mock.calls[2].request)

    @respx.mock(base_url=BASE_URL)
    async def test_cookie_then_bearer_then_cookie(self, api_client, respx_mock):
        respx_mock.get("/core/v1/reward/brand/1").respond(200, json=OK_JSON)
        respx_mock.get("/arya/api/v1/org/list").respond(200, json=OK_JSON)
        respx_mock.get("/arya/api/v1/nfs/filters/").respond(200, json=OK_JSON)

        await api_client.reward.list_catalog_rewards(1)
        assert_cookie_auth(respx_mock.calls[0].request)

        await api_client.arya.get_org_list()
        assert_bearer_auth(respx_mock.calls[1].request)

        await api_client.audience.get_audience_filters()
        assert_cookie_auth(respx_mock.calls[2].request)

    @respx.mock(base_url=BASE_URL)
    async def test_all_four_markers_interleaved(self, api_client, respx_mock):
        """Hit one endpoint from each cookie-auth marker, interleaved with bearer."""
        respx_mock.get("/iris/v2/audience").respond(200, json=OK_JSON)
        respx_mock.get("/loyalty/api/v1/programs").respond(200, json=OK_JSON)
        respx_mock.get("/adiona/api/v1/attribution/default").respond(200, json=OK_JSON)
        respx_mock.get("/coupon/api/v1/config").respond(200, json=OK_JSON)
        respx_mock.get("/arya/api/v1/nfs/filters/").respond(200, json=OK_JSON)
        respx_mock.get("/arya/api/v1/org/list").respond(200, json=OK_JSON)
        respx_mock.get("/core/v1/fulfillmentStatus").respond(200, json=OK_JSON)

        await api_client.campaigns.get_audiences()
        assert_cookie_auth(respx_mock.calls[0].request)

        await api_client.loyalty.get_loyalty_programs()
        assert_bearer_auth(respx_mock.calls[1].request)

        await api_client.campaigns.get_default_attribution()
        assert_cookie_auth(respx_mock.calls[2].request)

        await api_client.coupon.list_coupon_series()
        assert_bearer_auth(respx_mock.calls[3].request)

        await api_client.audience.get_audience_filters()
        assert_cookie_auth(respx_mock.calls[4].request)

        await api_client.arya.get_org_list()
        assert_bearer_auth(respx_mock.calls[5].request)

        await api_client.reward.get_fulfillment_status()
        assert_cookie_auth(respx_mock.calls[6].request)

    @respx.mock(base_url=BASE_URL)
    async def test_campaign_api_mixed_within_service(self, api_client, respx_mock):
        """CampaignAPI mixes IRIS (cookie) and CREATIVES (bearer).
        This is the exact scenario that caused the original HTTP 520 bug."""
        respx_mock.get("/iris/v2/audience").respond(200, json=OK_JSON)
        respx_mock.get("/arya/api/v1/creatives/creatives/templates/v1/Sms").respond(
            200, json=OK_JSON
        )
        respx_mock.post("/iris/v2/campaigns/filter").respond(200, json=OK_JSON)

        await api_client.campaigns.get_audiences()
        assert_cookie_auth(respx_mock.calls[0].request)

        await api_client.campaigns.get_sms_templates()
        assert_bearer_auth(respx_mock.calls[1].request)

        await api_client.campaigns.list_campaigns()
        assert_cookie_auth(respx_mock.calls[2].request)
