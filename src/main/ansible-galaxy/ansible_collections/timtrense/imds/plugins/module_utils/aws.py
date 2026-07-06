import base64
from enum import Enum
from time import time

import requests, json
from ansible_collections.timtrense.imds.plugins.module_utils.imds_provider import CloudHostingProviderType, ImdsProvider, COMMON_IMDS_IPV4

class AwsIdentityDocumentInformation(Enum):
    # fields of the "instance identity document"
    ACCOUNT_ID = "accountId" # matches CommonInformation.ACCOUNT
    ARCHITECTURE = "architecture"
    BILLING_PRODUCTS = "billingProducts"
    DEVPAY_PRODUCT_CODES = "devpayProductCodes"
    MARKETPLACE_PRODUCT_CODES = "marketplaceProductCodes"
    IMAGE_ID = "imageId" # matches CommonInformation.IMAGE
    INSTANCE_ID = "instanceId" # matches CommonInformation.INSTANCE_ID
    INSTANCE_TYPE = "instanceType" # matches CommonInformation.INSTANCE_TYPE
    KERNEL_ID = "kernelId"
    PENDING_TIME = "pendingTime"
    PRIVATE_IP = "privateIp"
    RAMDISK_ID = "ramdiskId"
    REGION = "region" # matches CommonInformation.REGION
    VERSION = "version"

class AwsExtendedMetadataInformation(Enum):
    # fields of the /2026-04-15/meta-data endpoints
    RESERVATION_ID = "reservation-id"
    SECURITY_GROUPS = "security-groups"
    PUBLIC_IPV4 = "public-ipv4"
    LOCAL_IPV4 = "local-ipv4"
    HOSTNAME = "hostname"
    PROFILE = "profile"
    PUBLIC_HOSTNAME = "public-hostname"
    LOCAL_HOSTNAME = "local-hostname"
    INSTANCE_ACTION = "instance-action"
    INSTANCE_LIFECYCLE = "instance-life-cycle"
    SYSTEM = "system"
    AZ = "placement/availability-zone"
    AZ_ID = "placement/availability-zone-id"
    BLOCK_DEVICE_MAPPING_AMI = "block-device-mapping/ami"
    HIBERNATION_CONFIGURED = "hibernation/configured"

class AwsProvider(ImdsProvider):
    # IMDSv2 token caching
    _cached_token: str | None = None
    _cached_token_time: float | None = None
    _token_ttl_seconds: int = 60

    # payload response caching (this stuff won't realistically change across the lifetime of an ansible play)
    _cached_instance_identity: dict[str, any] | None = None
    _cached_extended_metadata: dict[str, any] = {}

    # instance userdata can only be changed in AWS upon EC2 instance reboot --> cacheable indefinitely during a single ansible play
    _cached_userdata_b64: str | None = None

    _API_VERSION = "2026-04-15"

    def __init__(self, params: dict[str, any] = {}, http_timeout_seconds: int | None = None):
        super().__init__(params=params, http_timeout_seconds=http_timeout_seconds)

    @staticmethod
    def _get_url(path: str) -> str:
        """Construct the full URL for the AWS IMDS endpoint."""
        return f"http://{COMMON_IMDS_IPV4}/{path}"

    def _get_v2_headers(self, additional_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Construct the headers for an IMDSv2 request."""
        headers = {"X-aws-ec2-metadata-token": self._get_v2_auth_token()}
        if additional_headers:
            headers.update(additional_headers)
        return headers

    def _get_v2_auth_token(self) -> str:
        """Query IMDSv2 auth token."""

        if self._cached_token and self._cached_token_time and (time() - self._cached_token_time) < self._token_ttl_seconds:
            return self._cached_token

        try:
            response_text = self._http_request(
                method="PUT",
                url=self._get_url("latest/api/token"), # sadly the token endpoint is not versioned?!
                headers={"X-aws-ec2-metadata-token-ttl-seconds": str(self._token_ttl_seconds)}
            )
            self._cached_token = response_text
            self._cached_token_time = time()
            return self._cached_token
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get IMDSv2 auth token: {e}", response=e.response)

    def _make_request(self, path: str) -> str:
        """Make a request to the AWS IMDS endpoint."""
        protocol_version = self.get_protocol_version()
        url = self._get_url(path)

        if protocol_version == "2":
            token = self._get_v2_auth_token()
            try:
                return self._http_request(method="GET", url=url, headers={"X-aws-ec2-metadata-token": token})
            except requests.RequestException as e:
                raise requests.RequestException(f"Failed to get IMDSv2 metadata at AWS: {e}", response=e.response)
        else:
            try:
                return self._http_request(method="GET", url=url)
            except requests.RequestException as e:
                raise requests.RequestException(f"Failed to get IMDSv1 metadata at AWS: {e}", response=e.response)

    def _query_instance_identity_document(self) -> dict[str, any]:
        if self._cached_instance_identity is None:
            self._cached_instance_identity = json.loads(self._make_request(f"{self._API_VERSION}/dynamic/instance-identity/document"))
        return self._cached_instance_identity

    def _query_extended_metadata(self, field: str) -> str:
        if field not in self._cached_extended_metadata:
            self._cached_extended_metadata[field] = self._make_request(f"{self._API_VERSION}/meta-data/{field}")
        return self._cached_extended_metadata[field]

    def get_supported_informations(self) -> set[str]:
        return super().get_supported_informations() \
            | {info.name.lower() for info in AwsIdentityDocumentInformation} \
            | {info.name.lower() for info in AwsExtendedMetadataInformation}

    def query(self, info: str) -> str:
        try:
            return super().query(info)
        except NotImplementedError:
            pass # okay, we will try the proprietary information next

        if info.upper() in AwsIdentityDocumentInformation.__members__:
            return self._query_instance_identity_document().get(AwsIdentityDocumentInformation[info.upper()].value, None)

        if info.upper() in AwsExtendedMetadataInformation.__members__:
            strval = self._query_extended_metadata(AwsExtendedMetadataInformation[info.upper()].value)
            if info.upper() == AwsExtendedMetadataInformation.HIBERNATION_CONFIGURED.name:
                return bool(strval.lower() == "true") # convert to boolean
            return strval

        raise NotImplementedError(f"AWS provider does not support querying information \"{info}\".")

    def detect(self) -> bool:
        """Detect whether we are running on an AWS EC2 instance."""
        try:
            self._make_request(f"{self._API_VERSION}/meta-data/instance-id")
            return True
        except requests.RequestException:
            return False

    def get_type(self) -> CloudHostingProviderType:
        return CloudHostingProviderType.AWS

    def get_protocol_version(self) -> str:
        """Determine the IMDS protocol version."""
        if self._cached_token:
            return "2" # we only query a token, if we are on IMDSv2, so if we have a cached token, we are on IMDSv2

        # testing whether we can query a token. if so, we prefer using v2 and only fallback to v1 otherwise
        try:
            token = self._get_v2_auth_token()
            if token:
                return "2"
        except requests.RequestException:
            pass

        return "1"

    def _get_raw_availability_zone(self):
        """Returns the proprietary AWS availability zone name (which really is region+az)."""
        az = self._query_instance_identity_document().get("availabilityZone", "")
        if not az:
            raise ValueError("Failed to retrieve availability zone from AWS IMDS instance identity document.")
        return az

    def get_instance_id(self):
        return self._query_instance_identity_document().get("instanceId", "")

    def get_instance_type(self):
        return self._query_instance_identity_document().get("instanceType", "")

    def get_image(self):
        return self._query_instance_identity_document().get("imageId", "")

    def get_availability_zone(self):
        raw_az = self._get_raw_availability_zone()
        # AWS returns "eu-central-1a" for example, so we just return the last character
        return raw_az[-1]

    def get_region(self):
        raw_az = self._get_raw_availability_zone()
        # AWS returns "eu-central-1a" for example, so we just return everything except the last character
        return raw_az[:-1]

    def get_resource_group(self):
        # AWS does not have a resource group, so we return the account ID instead
        return self.get_account()

    def get_account(self):
        return self._query_instance_identity_document().get("accountId", "")

    def get_tags(self):
        # this might or might not work: access to tags can be disabled
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/work-with-tags-in-IMDS.html
        return json.loads(self._query_extended_metadata("tag-sets/instance"))

    def get_userdata(self):
        if self._cached_userdata_b64 is None:
            import requests

            response = requests.request(
                method="GET",
                url=self._get_url(f"{self._API_VERSION}/user-data"),
                headers=self._get_v2_headers(additional_headers=None),
                timeout=self.http_timeout_seconds
            )
            if response.status_code == 200:
                content = response.content
                if content is not None and len(content) > 0:
                    self._cached_userdata_b64 = base64.b64encode(response.content, altchars=b"-_").decode()

        # self._cached_userdata_b64 might still be None if the user-data is empty or not set, so we return None in that case
        return self._cached_userdata_b64
