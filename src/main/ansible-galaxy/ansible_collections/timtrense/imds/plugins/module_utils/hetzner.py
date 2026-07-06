import base64
import binascii
from enum import Enum
from functools import reduce

import requests, yaml
from ansible_collections.timtrense.imds.plugins.module_utils.imds_provider import CloudHostingProviderType, CommonInformation, ImdsProvider, COMMON_IMDS_IPV4

class HetznerInstanceInformation(Enum):
    # fields of the "instance document"
    VENDOR_DATA = "vendor_data"
    LOCAL_IPV4 = "local-ipv4"
    PUBLIC_IPV4 = "public-ipv4"

class HetznerProvider(ImdsProvider):
    # payload response caching (this stuff won't realistically change across the lifetime of an ansible play)
    _cached_instance: dict[str, any] | None = None
    _cached_userdata_b64: str | None = None
    """URL-safe base64-encoded user data, as returned by Hetzner IMDS"""

    _PROTOCOL_VERSION = "1"

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

    def _has_api_token(self) -> bool:
        """Check whether an API token was configured."""
        return self.params.get(f"{CloudHostingProviderType.HZ.value}_api_token", None) is not None

    def get_supported_informations(self) -> set[str]:
        if not self._has_api_token():
            return {
                CommonInformation.CLOUD_HOSTING_PROVIDER.name.lower(),
                CommonInformation.IMDS_VERSION.name.lower(),
                CommonInformation.INSTANCE_ID.name.lower(),
                # CommonInformation.INSTANCE_TYPE.name.lower(),
                # CommonInformation.IMAGE.name.lower(),
                CommonInformation.AVAILABILITY_ZONE.name.lower(),
                CommonInformation.REGION.name.lower(),
                # CommonInformation.RESOURCE_GROUP.name.lower(),
                # CommonInformation.ACCOUNT.name.lower(),
                # CommonInformation.TAGS.name.lower(),
                CommonInformation.USERDATA.name.lower(),
                HetznerInstanceInformation.VENDOR_DATA.name.lower(),
                HetznerInstanceInformation.LOCAL_IPV4.name.lower(),
                HetznerInstanceInformation.PUBLIC_IPV4.name.lower(),
            }
        return super().get_supported_informations() \
            | {info.name.lower() for info in HetznerInstanceInformation}

    def query(self, info: str) -> str:
        try:
            return super().query(info)
        except NotImplementedError:
            pass # okay, we will try the proprietary information next

        if info.upper() in HetznerInstanceInformation.__members__:
            path = HetznerInstanceInformation[info.upper()].value.split(".")
            result = reduce(lambda d, k: d.get(k) if isinstance(d, dict) else None, path, self._query())
            if result == "":
                result=None
            return result

        raise NotImplementedError(f"Hetzner provider does not support querying information \"{info}\".")

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
        return str(self._query().get("instance-id", None))

    def get_instance_type(self):
        return "unknown" # TODO: query hetzner api

    def get_image(self):
        return "unknown" # TODO: query hetzner api

    def get_availability_zone(self):
        return self._query().get("availability-zone", None)

    def get_region(self):
        return self._query().get("region", None)

    def get_resource_group(self):
        return "unknown" # TODO: query hetzner api for project name

    def get_account(self):
        return "unknown" # TODO: query hetzner api for account name

    def get_tags(self):
        return {} # TODO: query hetzner api for server labels

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
