"""
Capillary Platform API Client — async httpx port.

Ported from ``final_config_apis.ipynb`` cell 4.
All 13 service classes, 89 methods, 15 service-path mappings.
Token is passed in (no global credentials).
"""

from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Literal, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service path mappings
# ---------------------------------------------------------------------------

SERVICE_PATHS: Dict[str, str] = {
    "ARYA": "/arya/api/v1",
    "EMF": "/loyalty/emf/v1",
    "INTOUCH_API": "/v2",
    "INTOUCH_V3_API": "/v3",
    "IRIS": "/iris/v2",
    "COUPONS_API": "/coupon/api/v1",
    "LOYALTY": "/loyalty/api/v1",
    "INCENTIVES": "/incentives/api/v1",
    "ORG_SETTINGS": "/arya/api/v1/org-settings",
    "PROMOTION_MANAGEMENT": "/v1/promotion-management",
    "NSE": "/arya/api/v1/nse",
    "NFS": "/arya/api/v1/nfs",
    "CREATIVES": "/arya/api/v1/creatives",
    "REWARD_CORE": "/core/v1",
    "ADIONA": "/adiona/api/v1",
    "NSE_API": "/reonexport/v1",
}

# Paths that require cookie-based auth instead of Bearer token
_COOKIE_AUTH_MARKERS = ("/iris/", "/adiona/", "/nse/", "/nfs/", "/core/v1/")

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 60.0  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class APIError(Exception):
    """Custom exception for API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response


# ---------------------------------------------------------------------------
# BaseAPIClient — async httpx
# ---------------------------------------------------------------------------

class BaseAPIClient:
    """Base API client with authentication and request handling (async)."""

    def __init__(
        self,
        host: str,
        token: Optional[str] = None,
        org_id: Optional[int] = None,
    ):
        self.host = host.rstrip("/")
        self.token = token
        self.org_id = org_id
        self.base_url = f"https://{self.host}"

        # Shared async client (caller must close via ``aclose()``)
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=REQUEST_TIMEOUT,
            headers=self._default_headers(),
        )

    # -- helpers --

    def _default_headers(self) -> Dict[str, str]:
        """Non-auth headers only — auth is handled per-request by _prepare_headers()
        to avoid httpx client-level header merge leaking Authorization into
        cookie-auth requests."""
        return {"Accept": "application/json"}

    def _needs_cookie_auth(self, url: str) -> bool:
        return any(marker in url for marker in _COOKIE_AUTH_MARKERS)

    def _prepare_headers(
        self, url: str, headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Build final headers with full auth control.

        Auth headers are NOT in the httpx client defaults (to prevent
        httpx from merging ``Authorization`` back into cookie-auth
        requests).  Instead, this method adds auth headers explicitly:
        - Cookie-auth paths → ``Cookie: CT=…; OID=…`` (no ``Authorization``)
        - Bearer-auth paths → ``Authorization: Bearer …``
        """
        merged: Dict[str, str] = dict(self._http.headers)
        if headers:
            merged.update(headers)

        if self._needs_cookie_auth(url):
            # --- cookie-auth conversion ---
            org_id = merged.get("X-CAP-API-AUTH-ORG-ID") or (
                str(self.org_id) if self.org_id else None
            )
            if not org_id:
                raise APIError(
                    "org_id is required for IRIS/ADIONA/NSE/CORE endpoints."
                )
            merged["X-CAP-API-AUTH-ORG-ID"] = org_id
            merged["X-CAP-ORG"] = org_id

            # Extract token
            token: Optional[str] = None
            auth_hdr = merged.get("Authorization", "")
            if auth_hdr.startswith("Bearer "):
                token = auth_hdr.removeprefix("Bearer ")
            elif self.token:
                token = self.token
            if not token:
                raise APIError(
                    "Authentication token is required for IRIS/ADIONA endpoints."
                )

            merged["Cookie"] = f"CT={token}; OID={org_id}"
            merged.pop("Authorization", None)
            merged["User-Agent"] = _BROWSER_UA

            if "X-CAP-REQUEST-ID" not in merged:
                merged["X-CAP-REQUEST-ID"] = str(uuid.uuid4())
        else:
            # --- Bearer auth (added per-request, not in client defaults) ---
            if "Authorization" not in merged and self.token:
                merged["Authorization"] = f"Bearer {self.token}"
            if "X-CAP-API-AUTH-ORG-ID" not in merged and self.org_id:
                merged["X-CAP-API-AUTH-ORG-ID"] = str(self.org_id)

        return merged

    @staticmethod
    def _check_api_response(data: Any, status_code: int) -> None:
        """Raise ``APIError`` if the JSON body indicates failure."""
        if not isinstance(data, dict):
            return
        # Top-level success=False
        if data.get("success") is False:
            raise APIError(
                f"API returned success=False: {data.get('message', 'Unknown')}",
                status_code=status_code,
                response=data,
            )
        # Nested status object
        status = data.get("status")
        if isinstance(status, dict):
            code = status.get("code")
            if code is not None and code not in (200, 201):
                raise APIError(
                    f"API error code {code}: {status.get('message', 'Unknown')}",
                    status_code=code,
                    response=data,
                )
            if status.get("success") is False:
                raise APIError(
                    f"API returned success=False: {status.get('message', 'Unknown')}",
                    status_code=status_code,
                    response=data,
                )

    # -- core request methods --

    async def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else path
        req_headers = self._prepare_headers(
            path if not path.startswith("http") else path, headers
        )
        try:
            resp = await self._http.get(url, params=params, headers=req_headers)
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError:
                return {"text": resp.text}
            self._check_api_response(data, resp.status_code)
            return data
        except httpx.HTTPStatusError as exc:
            raise APIError(
                f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
                status_code=exc.response.status_code,
                response=exc.response.text,
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Request failed: {exc}") from exc

    async def _post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else path
        req_headers = self._prepare_headers(
            path if not path.startswith("http") else path, headers
        )
        try:
            resp = await self._http.post(
                url, json=json, params=params, headers=req_headers
            )
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError:
                return {"text": resp.text}
            self._check_api_response(data, resp.status_code)
            return data
        except httpx.HTTPStatusError as exc:
            raise APIError(
                f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
                status_code=exc.response.status_code,
                response=exc.response.text,
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Request failed: {exc}") from exc

    async def _get_binary(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        url = path if path.startswith("http") else path
        req_headers: Dict[str, str] = {}
        if headers:
            req_headers.update(headers)
        try:
            resp = await self._http.get(url, params=params, headers=req_headers)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError as exc:
            raise APIError(
                f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
                status_code=exc.response.status_code,
                response=exc.response.text,
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(f"Request failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._http.aclose()

    # context-manager support
    async def __aenter__(self) -> "BaseAPIClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()


# ---------------------------------------------------------------------------
# CouponAPI — 7 methods
# ---------------------------------------------------------------------------

class CouponAPI:
    """Coupon configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["COUPONS_API"]

    async def list_coupon_series(
        self,
        program_id: Optional[int] = None,
        owned_by: Optional[Literal["LOYALTY"]] = None,
        include_unclaimed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params["ownedBy"] = owned_by if owned_by is not None else "NONE"
        if program_id is not None:
            params["ownerId"] = program_id
        if include_unclaimed is True:
            params["includeUnclaimed"] = "true"
        return await self.client._get(
            f"{self.base_path}/config", params=params or None
        )

    async def get_coupon_series_by_id(self, series_id: int) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/config/{series_id}")

    async def get_custom_property(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/customProperty")

    async def get_org_settings(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/orgSettings")

    async def get_product_categories(
        self,
        parent_id: Optional[int] = None,
        include_children: bool = False,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if parent_id is not None:
            params["parent_id"] = parent_id
        if include_children:
            params["include_children"] = "true"
        return await self.client._get(
            f"{self.base_path}/entity/product/categories",
            params=params or None,
        )

    async def get_product_brands(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/entity/product/brands"
        )

    async def get_product_attributes(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/entity/product/attributes"
        )


# ---------------------------------------------------------------------------
# LoyaltyAPI — 19 methods
# ---------------------------------------------------------------------------

class LoyaltyAPI:
    """Loyalty Program configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["LOYALTY"]

    async def get_loyalty_programs(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/programs")

    async def get_loyalty_program_by_id(self, program_id: int) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/programs/{program_id}")

    async def get_all_partner_programs_by_lp_id(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/programs/partner-programs/{program_id}"
        )

    async def get_all_tiers_by_lp_id(self, program_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/programs/tiers/{program_id}"
        )

    async def get_strategies(self, program_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/strategy/points/{program_id}"
        )

    async def get_liability_owners(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/liability/liabilityOwners"
        )

    async def get_custom_fields(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/settings/custom-field"
        )

    async def get_ruleset_scoping(
        self, scope_type: Literal["CustomerCluster", "EventSource"]
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/workflows/rulesets-scoping/scope",
            params={"type": scope_type},
        )

    async def get_org_labels(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/workflows/org-labels"
        )

    async def get_event_types(
        self,
        program_id: int | str,
        source: Optional[Literal["PROMOTION"]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if source:
            params["source"] = source
        return await self.client._get(
            f"{self.base_path}/workflows/event-types/{program_id}",
            params=params or None,
        )

    async def list_promotions(
        self, limit: int = 50, offset: int = 0
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if self.client.org_id:
            headers["X-CAP-API-AUTH-ORG-ID"] = str(self.client.org_id)
        return await self.client._get(
            f"{SERVICE_PATHS['EMF']}/programs/promotions/list",
            params={"limit": limit, "offset": offset},
            headers=headers or None,
        )

    async def get_promotion(
        self, promotion_id: int, program_id: int
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if self.client.org_id:
            headers["X-CAP-API-AUTH-ORG-ID"] = str(self.client.org_id)
        return await self.client._get(
            f"{SERVICE_PATHS['EMF']}/programs/{program_id}/promotions/{promotion_id}/get",
            headers=headers or None,
        )

    async def get_liability_split(self, promotion_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/liability/liabilityOwnersForComponent/PROMOTION/{promotion_id}"
        )

    async def get_line_item_extended_fields(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/trackers/extendedFields/{program_id}/LINEITEM_EXTENDED_FIELD",
            params={
                "allowedFieldTypes": "DATETIME,DATE,INTEGER,STRING,BOOLEAN,DOUBLE"
            },
        )

    async def get_txn_extended_fields(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/trackers/extendedFields/{program_id}/BILL_EXTENDED_FIELD",
            params={
                "allowedFieldTypes": "DATETIME,DATE,INTEGER,STRING,BOOLEAN,DOUBLE"
            },
        )

    async def get_customer_extended_fields(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/trackers/extendedFields/{program_id}/CUSTOMER_EXTENDED_FIELD",
            params={
                "allowedFieldTypes": "DATETIME,DATE,INTEGER,STRING,BOOLEAN,DOUBLE"
            },
        )

    async def get_alternate_currencies(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/alternateCurrency/{program_id}",
            params={"pageSize": 1000, "pageNum": 0},
        )

    async def get_subscription_partner_programs(
        self, program_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/partner-program/{program_id}"
        )

    async def get_tender_combination_types(
        self, garbage_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/strategy/tender-combination/types/{garbage_id}"
        )


# ---------------------------------------------------------------------------
# CampaignAPI — 24 methods
# ---------------------------------------------------------------------------

class CampaignAPI:
    """Campaign (IRIS) configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["IRIS"]

    def _org_headers(self) -> Optional[Dict[str, str]]:
        if self.client.org_id:
            return {"X-CAP-API-AUTH-ORG-ID": str(self.client.org_id)}
        return None

    async def get_audiences(self, search: str = "") -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/audience",
            params={"limit": 10, "offset": 0, "search": search},
            headers=self._org_headers(),
        )

    async def get_audience_by_id(self, aid: str) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/audience/{aid}",
            headers=self._org_headers(),
        )

    async def list_campaigns(
        self, campaign_name: str = "", limit: int = 10
    ) -> Dict[str, Any]:
        return await self.client._post(
            f"{self.base_path}/campaigns/filter",
            json={"limit": limit, "search": campaign_name},
            headers=self._org_headers(),
        )

    async def get_campaign_by_id(self, campaign_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/campaigns/{campaign_id}",
            headers=self._org_headers(),
        )

    async def get_default_attribution(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['ADIONA']}/attribution/default",
            headers=self._org_headers(),
        )

    async def get_referral_and_survey(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/campaigns/type",
            params={"type": ["SURVEY", "REFERRAL"]},
            headers=self._org_headers(),
        )

    async def get_sms_templates(
        self, trai_enabled: bool = False
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if trai_enabled:
            params["traiEnable"] = "true"
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/Sms",
            params=params or None,
            headers=self._org_headers(),
        )

    async def get_email_templates(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/Email",
            headers=self._org_headers(),
        )

    async def get_domain_properties(self, channel: str) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/org/campaign/meta/domainProperties",
            params={"channel": channel},
            headers=self._org_headers(),
        )

    async def get_brand_point_of_contact(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/audience",
            params={"types": "ORG_USERS"},
            headers=self._org_headers(),
        )

    async def get_program_configurations(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/org/campaign/meta/loyaltyProgram",
            headers=self._org_headers(),
        )

    async def get_whatsapp_accounts(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/meta/wecrm",
            params={"source_name": "WHATSAPP"},
            headers=self._org_headers(),
        )

    async def get_whatsapp_templates(
        self, account_id: str, host_name: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/WhatsApp",
            params={"accountId": account_id, "host": host_name},
            headers=self._org_headers(),
        )

    async def get_push_notification_accounts(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/meta/wecrm",
            params={"source_name": "MOBILEPUSH"},
            headers=self._org_headers(),
        )

    async def get_push_notification_templates(
        self, account_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/MobilePush",
            params={"accountId": account_id},
            headers=self._org_headers(),
        )

    async def list_campaign_messages(
        self, campaign_id: int, limit: int = 10, offset: int = 0
    ) -> Dict[str, Any]:
        return await self.client._post(
            f"{self.base_path}/campaigns/{campaign_id}/messages/filter",
            json={"limit": limit, "offset": offset},
            headers=self._org_headers(),
        )

    async def get_campaign_message_by_id(
        self, campaign_id: int, message_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/campaigns/{campaign_id}/messages/{message_id}",
            headers=self._org_headers(),
        )

    async def check_message_name_already_exists(
        self, campaign_id: int, message_name: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/campaigns/{campaign_id}/messages/checkExists",
            params={"name": message_name},
            headers=self._org_headers(),
        )

    async def check_campaign_name_already_exists(
        self, campaign_name: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/campaigns/checkExists",
            params={"name": campaign_name},
            headers=self._org_headers(),
        )

    async def get_sms_template_by_id(self, template_id: str) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/{template_id}/SMS",
            headers=self._org_headers(),
        )

    async def get_email_template_by_id(
        self, template_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/{template_id}/EMAIL",
            headers=self._org_headers(),
        )

    async def get_email_template_content(
        self, template_url: str
    ) -> str:
        data = await self.client._get(
            template_url, headers=self._org_headers()
        )
        return data.get("text", "") if isinstance(data, dict) else ""

    async def get_push_notification_template_by_id(
        self, template_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/templates/v1/{template_id}/SMS",
            headers=self._org_headers(),
        )

    async def get_central_communication_by_meta_ids(
        self,
        meta_ids: List[str],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        meta_ids_str = ",".join(meta_ids)
        headers: Dict[str, str] = {}
        if user_id:
            headers["X-CAP-REMOTE-USER"] = str(user_id)
        if self.client.org_id:
            headers["X-CAP-API-AUTH-ORG-ID"] = str(self.client.org_id)
        return await self.client._get(
            f"{SERVICE_PATHS['CREATIVES']}/creatives/common/central-comms/meta-id/TRANSACTION",
            params={"metaIds": meta_ids_str},
            headers=headers or None,
        )


# ---------------------------------------------------------------------------
# PromotionAPI — 11 methods
# ---------------------------------------------------------------------------

class PromotionAPI:
    """Promotion configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["PROMOTION_MANAGEMENT"]

    async def get_cart_promo_or_gift_voucher_by_id(
        self, promotion_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/promotions/{promotion_id}"
        )

    async def get_cart_promo_or_gift_voucher_by_name(
        self,
        name: Optional[str] = None,
        promotion_types: Optional[str] = None,
        promotion_mode: Optional[str] = None,
        active: Optional[bool] = None,
        campaign_id: Optional[int] = None,
        unclaimed_only: Optional[bool] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if name:
            params["name"] = name
        if promotion_types:
            params["promotionTypes"] = promotion_types
        if promotion_mode:
            params["promotionMode"] = promotion_mode
        if active is not None:
            params["active"] = "true" if active else "false"
        if campaign_id is not None:
            params["campaignId"] = campaign_id
        if unclaimed_only is not None:
            params["unclaimedOnly"] = "true" if unclaimed_only else "false"
        return await self.client._get(
            f"{self.base_path}/promotions/filters",
            params=params or None,
        )

    async def get_vendors_list(self, brand_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/vendors/list/brand/{brand_id}"
        )

    async def get_vendor_redemptions_list(
        self,
        redemption_type: Optional[str] = None,
        brand_id: Optional[int] = None,
        vendor_id: Optional[int] = None,
        vendor_redemption_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        base_url = f"{SERVICE_PATHS['INCENTIVES']}/rewards/vendors"
        if vendor_redemption_id is None and brand_id is None and redemption_type is not None:
            url = f"{base_url}/vendor/redemption/list"
            params: Dict[str, Any] = {"redemptionType": redemption_type}
            if vendor_id is not None:
                params["vendorId"] = vendor_id
        else:
            url = f"{base_url}/vendor/{vendor_id}/redemption/{vendor_redemption_id}/brand/{brand_id}"
            params = None  # type: ignore[assignment]
        return await self.client._get(url, params=params)

    async def get_segments_list(self) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if self.client.org_id:
            headers["X-CAP-API-AUTH-ORG-ID"] = str(self.client.org_id)
        return await self.client._get(
            f"{SERVICE_PATHS['NSE']}/nse/segmentation-api/v2/segments",
            params={"isActive": "true"},
            headers=headers or None,
        )

    async def get_categories_list(self, brand_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/settings/category/brand/{brand_id}"
        )

    async def get_languages_list(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/settings/languages",
            params={"status": "ENABLED"},
        )

    async def get_groups_list(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/settings/groups",
            params={
                "orderBy": "DESC",
                "sortOn": "LAST_UPDATED_ON",
                "size": 10000,
            },
        )

    async def get_custom_fields_list(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/settings/custom-fields/unified-cf-rc",
            params={"transformForLinking": "true", "scope": "REWARD"},
        )

    async def get_reward_response_by_id(
        self, reward_id: int, brand_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/reward/{reward_id}/brand/{brand_id}"
        )

    async def get_rewards_list(
        self, brand_id: int, reward_name: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['INCENTIVES']}/rewards/list/brand/{brand_id}",
            params={"rewardName": reward_name, "sortOn": "LAST_UPDATED_ON"},
        )


# ---------------------------------------------------------------------------
# RewardAPI — 4 methods
# ---------------------------------------------------------------------------

class RewardAPI:
    """Reward configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["REWARD_CORE"]

    def _org_headers(self) -> Optional[Dict[str, str]]:
        if self.client.org_id:
            return {"X-CAP-API-AUTH-ORG-ID": str(self.client.org_id)}
        return None

    async def list_catalog_rewards(self, brand_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/reward/brand/{brand_id}",
            headers=self._org_headers(),
        )

    async def get_brands(
        self, org_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        org_id_list = org_ids or (
            [self.client.org_id] if self.client.org_id else []
        )
        return await self.client._post(
            f"{self.base_path}/brand/getAll",
            json={"orgIds": org_id_list},
            headers=self._org_headers(),
        )

    async def get_fulfillment_status(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/fulfillmentStatus",
            headers=self._org_headers(),
        )

    async def get_custom_fields(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/brand/customfield",
            headers=self._org_headers(),
        )


# ---------------------------------------------------------------------------
# OrgSettingsAPI — 6 methods
# ---------------------------------------------------------------------------

class OrgSettingsAPI:
    """Organization Settings endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["ORG_SETTINGS"]

    async def get_till_details(self, till_code: str) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/target-groups/till-credentials",
            params={"code": till_code},
        )

    async def get_all_target_groups(
        self, name: Optional[str] = None
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "limit": 10000,
            "offset": 0,
            "type": "DEFAULT~UNIFIED~STREAKS~NON_CONTINUOUS_STREAKS",
        }
        if name:
            params["name"] = name
        return await self.client._get(
            f"{self.base_path}/target-groups/targets", params=params
        )

    async def get_tg_by_id(self, tg_id: int) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/target-groups/targetGroup/{tg_id}",
            params={"includePeriods": "true"},
        )

    async def get_periods_for_target_group(
        self, target_group_id: int
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/target-groups/targetGroups/targetPeriods/{target_group_id}"
        )

    async def get_behavioral_events(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/events/list")

    async def get_customer_labels(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/customer-status-configuration/labels"
        )


# ---------------------------------------------------------------------------
# CartPromotionAPI — 2 methods
# ---------------------------------------------------------------------------

class CartPromotionAPI:
    """Cart Promotion configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["PROMOTION_MANAGEMENT"]

    async def get_custom_fields_for_cart_promotion(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/promotions/settings/custom_field"
        )

    async def get_cart_promotion_features_by_id(
        self, cart_promotion_id: str, feature_type: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/promotions/{cart_promotion_id}/{feature_type}",
            headers={"Content-Type": "application/json"},
        )


# ---------------------------------------------------------------------------
# IntouchAPI — 1 method
# ---------------------------------------------------------------------------

class IntouchAPI:
    """Intouch configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["INTOUCH_API"]

    async def get_organization_hierarchy(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/organization/hierarchy"
        )


# ---------------------------------------------------------------------------
# AryaAPI — 3 methods
# ---------------------------------------------------------------------------

class AryaAPI:
    """Arya configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["ARYA"]

    async def get_entities(
        self, entity_type: Literal["STORE", "ZONE", "CONCEPT", "TILL"]
    ) -> Dict[str, Any]:
        if not self.client.org_id:
            raise APIError("org_id is required for get_entities")
        return await self.client._get(
            f"{self.base_path}/org/{self.client.org_id}/entities",
            params={"type": entity_type},
        )

    async def get_org_list(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/org/list")

    async def get_customers_count(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{SERVICE_PATHS['NFS']}/filters/customers"
        )


# ---------------------------------------------------------------------------
# FTPAPI — 1 method
# ---------------------------------------------------------------------------

class FTPAPI:
    """FTP configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["NSE_API"]

    async def get_ftp_credentials(
        self, org_id: int, ftp_tag: str
    ) -> Dict[str, Any]:
        headers = {
            "X-CAP-API-AUTH-ORG-ID": str(org_id),
            "X-CAP-API-AUTH-USER-ID": "-1",
            "X-CAP-API-AUTH-MODULE": "export",
            "X-CAP-REQUEST-ID": "ftp-export-request",
        }
        return await self.client._get(
            f"{self.base_path}/orgs/{org_id}/ftp/{ftp_tag}/",
            headers=headers,
        )


# ---------------------------------------------------------------------------
# AudienceAPI — 6 methods
# ---------------------------------------------------------------------------

class AudienceAPI:
    """Audience/NFS configuration endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = SERVICE_PATHS["NFS"]

    async def get_dim_attr_values(
        self, dimension: str, attribute: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/meta/getdimensionattrvalues/{dimension}/{attribute}"
        )

    async def search_dim_attr_values(
        self, dimension: str, attribute: str, search_term: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/meta/searchdimensionattrvalues/{dimension}/{attribute}/{search_term}/true"
        )

    async def get_hierarchy_data_via_dimension(
        self, dimension: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/meta/getmultidimensions/{dimension}"
        )

    async def get_dim_attr_value_availability(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/meta/getdimattrvalueavailability"
        )

    async def get_audience_filters(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/filters/")

    async def get_customer_test_control(self) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/filters/customers",
            params={"context": "campaign"},
        )


# ---------------------------------------------------------------------------
# MySQLAPI — 1 method
# ---------------------------------------------------------------------------

class MySQLAPI:
    """MySQL event query endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = "/ask-aira/copilot/mysql"

    async def get_events(
        self,
        event_type: Literal["promotions", "voucher_series", "target_groups"],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        sort: Optional[str] = None,
        shard: Optional[str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if limit:
            params["limit"] = limit
        if sort:
            params["sort"] = sort
        if shard:
            params["shard"] = shard
        headers: Dict[str, str] = {}
        if self.client.org_id:
            headers["X-CAP-API-AUTH-ORG-ID"] = str(self.client.org_id)
        return await self.client._get(
            f"{self.base_path}/events/{event_type}",
            params=params or None,
            headers=headers or None,
        )


# ---------------------------------------------------------------------------
# RAGAPI — 4 methods
# ---------------------------------------------------------------------------

class RAGAPI:
    """RAG / document source endpoints."""

    def __init__(self, client: BaseAPIClient):
        self.client = client
        self.base_path = "/ask-aira/copilot"

    async def get_contexts(self) -> Dict[str, Any]:
        return await self.client._get(f"{self.base_path}/get_contexts")

    async def get_context_attachment_file(
        self, context_name: str, file_name: str
    ) -> bytes:
        return await self.client._get_binary(
            f"{self.base_path}/get_context_attachment_file",
            params={"context_name": context_name, "file_name": file_name},
        )

    async def get_inference_view(
        self, inference_id: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/get_inference_view",
            params={"inference_id": inference_id},
        )

    async def download_org_payloads(
        self, org_id: str, version: str
    ) -> Dict[str, Any]:
        return await self.client._get(
            f"{self.base_path}/download_org_payloads",
            params={"org_id": org_id, "version": version},
        )


# ---------------------------------------------------------------------------
# CapillaryAPIClient — aggregator
# ---------------------------------------------------------------------------

class CapillaryAPIClient(BaseAPIClient):
    """Main Capillary API Client — aggregates all 13 service APIs."""

    def __init__(
        self,
        host: str,
        token: Optional[str] = None,
        org_id: Optional[int] = None,
    ):
        super().__init__(host, token, org_id)

        # Sub-clients
        self.coupon = CouponAPI(self)
        self.loyalty = LoyaltyAPI(self)
        self.campaigns = CampaignAPI(self)
        self.promotion = PromotionAPI(self)
        self.reward = RewardAPI(self)
        self.org_settings = OrgSettingsAPI(self)
        self.cart_promotion = CartPromotionAPI(self)
        self.intouch = IntouchAPI(self)
        self.arya = AryaAPI(self)
        self.ftp = FTPAPI(self)
        self.audience = AudienceAPI(self)
        self.rag = RAGAPI(self)
        self.mysql = MySQLAPI(self)
