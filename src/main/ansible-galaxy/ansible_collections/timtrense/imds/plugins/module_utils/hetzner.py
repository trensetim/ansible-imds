import base64
import binascii
from enum import Enum
from functools import reduce
import json

import requests, yaml
from ansible_collections.timtrense.imds.plugins.module_utils.imds_provider import CloudHostingProviderType, CommonInformation, ImdsProvider, COMMON_IMDS_IPV4

class HetznerInstanceInformation(Enum):
    # fields of the "instance document"
    VENDOR_DATA = "vendor_data"
    LOCAL_IPV4 = "local-ipv4"
    PUBLIC_IPV4 = "public-ipv4"

class HetznerExtendedInformation(Enum):
    # can be queried from the Hetzner API, but not from the IMDS endpoint
    RAW = "raw"
    CREATED = "created"
    STATUS = "status"
    LABELS = "labels"
    SERVER_TYPE_ID = "server_type.id"
    SERVER_TYPE_NAME = "server_type.name"
    SERVER_TYPE_DESCRIPTION = "server_type.description"
    SERVER_TYPE_DEPRECATED = "server_type.deprecated"
    LOCATION_ID = "location.id"
    LOCATION_NAME = "location.name"
    LOCATION_DESCRIPTION = "location.description"
    LOCATION_COUNTRY = "location.country"
    LOCATION_CITY = "location.city"
    LOCATION_NETWORK_ZONE = "location.network_zone"
    IMAGE_ID = "image.id"
    IMAGE_TYPE = "image.type"
    IMAGE_NAME = "image.name"
    IMAGE_DESCRIPTION = "image.description"
    IMAGE_DEPRECATED = "image.deprecated"
    IMAGE_DELETED = "image.deleted"
    PLACEMENT_GROUP_ID = "placement_group.id"
    PLACEMENT_GROUP_NAME = "placement_group.name"

class HetznerProvider(ImdsProvider):
    # payload response caching (this stuff won't realistically change across the lifetime of an ansible play)
    _cached_instance: dict[str, any] | None = None
    _cached_userdata_b64: str | None = None
    """URL-safe base64-encoded user data, as returned by Hetzner IMDS"""

    _cached_extended: dict[str, any] | None = None

    _PROTOCOL_VERSION = "1"
    _BASE_API_URL =  "https://api.hetzner.cloud/v1/"

    def __init__(self, params: dict[str, any] = {}, http_timeout_seconds: int | None = None):
        super().__init__(params=params, http_timeout_seconds=http_timeout_seconds)

    def _query(self) -> dict[str, any]:
        """Make a request to the Hetzner IMDS endpoint."""

        if self._cached_instance is not None:
            return self._cached_instance

        url = f"http://{COMMON_IMDS_IPV4}/hetzner/v{HetznerProvider._PROTOCOL_VERSION}/metadata"

        try:
            self._cached_instance = yaml.safe_load(self._http_request(method="GET", url=url))
            return self._cached_instance
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get IMDS metadata at Hetzner: {e}", response=e.response)

    def _query_extended(self, path: str) -> dict[str, any]:
        """Make a request to the Hetzner API endpoint for extended information."""
        if not self._has_api_token():
            raise ValueError("Hetzner API token is required to query extended information.")

        if self._cached_extended is not None:
            return self._cached_extended

        try:
            response = self._http_request(
                method="GET",
                url=f"{HetznerProvider._BASE_API_URL}{path}",
                headers={"Authorization": f"Bearer {self._get_api_token()}"}
            )
            self._cached_extended = json.loads(response)
            return self._cached_extended
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get extended information from Hetzner API: {e}", response=e.response)

    def _get_api_token(self) -> str | None:
        """Get the configured API token."""
        return self.params.get(f"{CloudHostingProviderType.HZ.value}_api_token", None)

    def _has_api_token(self) -> bool:
        """Check whether an API token was configured."""
        return self._get_api_token() is not None

    def get_supported_informations(self) -> set[str]:
        result = super().get_supported_informations() \
            | {info.name.lower() for info in HetznerInstanceInformation}
        if self._has_api_token():
            result = result | {info.name.lower() for info in HetznerExtendedInformation}
        return result

    def query(self, info: str) -> str:
        try:
            return super().query(info)
        except NotImplementedError:
            pass # okay, we will try the proprietary information next

        if info.upper() in HetznerInstanceInformation.__members__:
            result = self._query().get(HetznerInstanceInformation[info.upper()].value, None)
            if result == "":
                result = None
            return result

        if info.upper() in HetznerExtendedInformation.__members__:
            return self._query_extended_field(HetznerExtendedInformation[info.upper()])

        raise NotImplementedError(f"Hetzner provider does not support querying information \"{info}\".")

    def _query_extended_field(self, info: HetznerInstanceInformation) -> str | None:
        """Query a specific field from the Hetzner IMDS endpoint."""
        raw = self._query_extended(f"servers/{self.get_instance_id()}")

        if info == HetznerExtendedInformation.RAW:
            return raw

        path = info.value.split(".")
        return reduce(lambda d, k: d.get(k) if isinstance(d, dict) else None, path, raw["server"])

    def _possibly_query_extended_field(self, info: HetznerInstanceInformation) -> str:
        """Query a specific field from the Hetzner IMDS endpoint, if an API token is configured."""
        if not self._has_api_token():
            return "unknown"
        return self._query_extended_field(info)

    def detect(self) -> bool:
        """Detect whether we are running on a Hetzner VM."""
        try:
            self._query()
            return True
        except requests.RequestException:
            return False

    def get_type(self) -> CloudHostingProviderType:
        return CloudHostingProviderType.HZ

    def get_protocol_version(self) -> str:
        """Determine the IMDS protocol version."""
        return HetznerProvider._PROTOCOL_VERSION

    def get_instance_id(self):
        # allow overriding the instance id, for `delegate_to` scenarios where the play is run on a different host than the target VM
        if self.params.get(f"{CloudHostingProviderType.HZ.value}_instance_id", None) is not None:
            return self.params.get(f"{CloudHostingProviderType.HZ.value}_instance_id")

        return str(self._query().get("instance-id", None))

    def get_instance_type(self):
        return self._possibly_query_extended_field(HetznerExtendedInformation.SERVER_TYPE_NAME)

    def get_image(self):
        return self._possibly_query_extended_field(HetznerExtendedInformation.IMAGE_NAME)

    def get_availability_zone(self):
        return self._query().get("availability-zone", None)

    def get_region(self):
        return self._query().get("region", None)

    def get_resource_group(self):
        return self.params.get(f"{CloudHostingProviderType.HZ.value}_project", "unknown")

    def get_account(self):
        return self.params.get(f"{CloudHostingProviderType.HZ.value}_account", "unknown")

    def get_tags(self):
        result = self._possibly_query_extended_field(HetznerExtendedInformation.LABELS)
        if result == "unknown":
            return {}
        return result

    def get_userdata(self) -> str | None:
        if self._cached_userdata_b64 is not None:
            return self._cached_userdata_b64

        raw_b64_encoded_text: str = self._query().get("user_data", "")
        if raw_b64_encoded_text == "":
            return None

        # Hetzner Docs does not mention the base64 alphabet explicitly.
        # We assume standard RFC 4648, yet need to validate it
        raw_bytes: bytes
        try:
            raw_bytes = base64.b64decode(raw_b64_encoded_text, altchars=b"+/", validate=True)
        except binascii.Error:
            # in case the assumption breaks, we try again using the URL-safe base64 alphabet (which is also RFC 4648, but with different characters)
            # --> may throw again
            raw_bytes = base64.b64decode(raw_b64_encoded_text, altchars=b"-_", validate=True)

        self._cached_userdata_b64 = base64.b64encode(raw_bytes, altchars=b"-_").decode()
        return self._cached_userdata_b64
