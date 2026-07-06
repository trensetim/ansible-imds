import base64
import binascii
from enum import Enum
from functools import reduce

import requests, json
from ansible_collections.timtrense.imds.plugins.module_utils.imds_provider import CloudHostingProviderType, ImdsProvider, COMMON_IMDS_IPV4

class AzureInstanceInformation(Enum):
    # fields of the "instance document"
    ENVIRONMENT = "compute.azEnvironment"
    EVICTION_POLICY = "compute.evictionPolicy"
    OFFER = "compute.offer"
    HOST_COMPATIBILITY_LAYER_VM = "compute.isHostCompatibilityLayerVm"
    LICENSE_TYPE = "compute.licenseType"
    OS_TYPE = "compute.osType"
    PHYSICAL_ZONE = "compute.physicalZone"
    LOGICAL_ZONE = "compute.zone" # matches CommonInformation.AVAILABILITY_ZONE
    LOCATION = "compute.location" # matches CommonInformation.REGION
    PLACEMENT_GROUP_ID = "compute.placementGroupId"
    PLAN_NAME = "compute.plan.name"
    PLAN_PRODUCT = "compute.plan.product"
    PLAN_PUBLISHER = "compute.plan.publisher"
    PLATFORM_FAULT_DOMAIN = "compute.platformFaultDomain"
    PLATFORM_SUB_FAULT_DOMAIN = "compute.platformSubFaultDomain"
    PLATFORM_UPDATE_DOMAIN = "compute.platformUpdateDomain"
    PRIORITY = "compute.priority"
    PROVIDER = "compute.provider"
    PUBLISHER = "compute.publisher" # publisher of the image
    SKU = "compute.sku" # sku of the image
    RESOURCE_ID = "compute.resourceId"
    STORAGE_PROFILE_IMAGE_REFERENCE_ID = "compute.storageProfile.imageReference.id"
    STORAGE_PROFILE_IMAGE_REFERENCE_OFFER = "compute.storageProfile.imageReference.offer"
    STORAGE_PROFILE_IMAGE_REFERENCE_PUBLISHER = "compute.storageProfile.imageReference.publisher"
    STORAGE_PROFILE_IMAGE_REFERENCE_SKU = "compute.storageProfile.imageReference.sku"
    STORAGE_PROFILE_IMAGE_REFERENCE_VERSION = "compute.storageProfile.imageReference.version"
    STORAGE_PROFILE_IMAGE_REFERENCE_EXACT_VERSION = "compute.storageProfile.imageReference.exactVersion"
    STORAGE_PROFILE_OS_DISK_CACHING = "compute.storageProfile.osDisk.caching"
    STORAGE_PROFILE_OS_DISK_CREATE_OPTION = "compute.storageProfile.osDisk.createOption"
    STORAGE_PROFILE_OS_DISK_MANAGED_DISK_ID = "compute.storageProfile.osDisk.managedDisk.id"
    STORAGE_PROFILE_OS_DISK_MANAGED_DISK_STORAGE_ACCOUNT_TYPE = "compute.storageProfile.osDisk.managedDisk.storageAccountType"
    STORAGE_PROFILE_OS_DISK_NAME = "compute.storageProfile.osDisk.name"
    STORAGE_PROFILE_OS_TYPE = "compute.storageProfile.osType"
    SUBSCRIPTION_ID = "compute.subscriptionId" # matches CommonInformation.ACCOUNT
    TAGS_LIST = "compute.tagsList" # matches CommonInformation.TAGS
    VM_ID = "compute.vmId" # matches CommonInformation.INSTANCE_ID
    VM_SCALE_SET_NAME = "compute.vmScaleSetName"
    VM_SIZE = "compute.vmSize" # matches CommonInformation.INSTANCE_TYPE
    VERSION = "compute.version" # version of the image

class AzureProvider(ImdsProvider):
    # payload response caching (this stuff won't realistically change across the lifetime of an ansible play)
    _cached_instance: dict[str, any] | None = None
    _cached_userdata_b64: str | None = None
    """URL-safe base64-encoded user data, as returned by Azure IMDS"""

    _PROTOCOL_VERSION = "2025-11-11"

    def __init__(self, params: dict[str, any] = {}, http_timeout_seconds: int | None = None):
        super().__init__(params=params, http_timeout_seconds=http_timeout_seconds)

    def _query(self) -> dict[str, any]:
        """Make a request to the Azure IMDS endpoint."""

        if self._cached_instance is not None:
            return self._cached_instance

        url = f"http://{COMMON_IMDS_IPV4}/metadata/instance?api-version={AzureProvider._PROTOCOL_VERSION}&format=json"

        try:
            self._cached_instance = json.loads(self._http_request(method="GET", url=url, headers={"Metadata": "true"}))
            return self._cached_instance
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get IMDS metadata at Azure: {e}", response=e.response)

    def get_supported_informations(self) -> set[str]:
        return super().get_supported_informations() \
            | {info.name.lower() for info in AzureInstanceInformation}

    def query(self, info: str) -> str:
        try:
            return super().query(info)
        except NotImplementedError:
            pass # okay, we will try the proprietary information next

        if info.upper() in AzureInstanceInformation.__members__:
            path = AzureInstanceInformation[info.upper()].value.split(".")
            result = reduce(lambda d, k: d.get(k) if isinstance(d, dict) else None, path, self._query())
            if result == "":
                result=None
            return result

        raise NotImplementedError(f"Azure provider does not support querying information \"{info}\".")

    def detect(self) -> bool:
        """Detect whether we are running on an Azure VM."""
        try:
            self._query()
            return True
        except requests.RequestException:
            return False

    def get_type(self) -> CloudHostingProviderType:
        return CloudHostingProviderType.AZ

    def get_protocol_version(self) -> str:
        """Determine the IMDS protocol version."""
        return AzureProvider._PROTOCOL_VERSION

    def get_instance_id(self):
        return self._query().get("compute", {}).get("vmId", "")

    def get_instance_type(self):
        return self._query().get("compute", {}).get("vmSize", "")

    def get_image(self):
        publisher = self._query().get("compute", {}).get("publisher", "")
        sku = self._query().get("compute", {}).get("sku", "")
        version = self._query().get("compute", {}).get("version", "")
        return f"{publisher}:{sku}:{version}"

    def get_availability_zone(self):
        return self._query().get("compute", {}).get("zone", "")

    def get_region(self):
        return self._query().get("compute", {}).get("location", "")

    def get_resource_group(self):
        return self._query().get("compute", {}).get("resourceGroupName", "")

    def get_account(self):
        return self._query().get("compute", {}).get("subscriptionId", "")

    def get_tags(self):
        tagslist: list[dict[str, str]] = self._query().get("compute", {}).get("tagsList", [])
        return {tag["name"]: tag["value"] for tag in tagslist}

    def get_userdata(self) -> str | None:
        if self._cached_userdata_b64 is not None:
            return self._cached_userdata_b64

        raw_b64_encoded_text: str = self._query().get("compute", {}).get("userData", "")
        if raw_b64_encoded_text == "":
            return None

        # Azure Docs does not mention the base64 alphabet explicitly.
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
