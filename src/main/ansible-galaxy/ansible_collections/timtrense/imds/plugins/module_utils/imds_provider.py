from enum import Enum
from collections.abc import abstractmethod

COMMON_IMDS_IPV4 = "169.254.169.254"
COMMON_IMDS_IPV6 = "fd00:ec2::254"

class CloudHostingProviderType(Enum):
    """Lists the known cloud hosting providers."""
    AWS = "amazon"
    AZ = "azure"
    GCP = "google"
    HZ = "hetzner"

class CommonInformation(Enum):
    """
    Nearly all cloud hosting providers provide some basic information via their IMDS, so we can query that in a provider-agnostic way.

    Each provider may support non-common additional information as well.

    There are certainly some other/more common information that could be added here,
    but we intentionally keep this list as short as possible.
    Why? - because for information like "hostname" or "ip address" or "mounted disks" or "network interfaces"
    there are other ansible modules to query such information, so we don't need to duplicate that here.
    Furthermore, these concepts deviate slightly between providers, making it error prone for users to rely
    on such information, if we were to report it "agnostically".
    """

    # invented by this module, not part of the IMDS
    CLOUD_HOSTING_PROVIDER = "cloud_hosting_provider"
    IMDS_VERSION = "imds_version"

    # common informations found by IMDS across nearly all cloud providers
    INSTANCE_ID = "id"
    """AWS instanceId, Azure vmId, GCP id, Hetzner serverId"""
    INSTANCE_TYPE = "type"
    """AWS instanceType, Azure vmSize, GCP machineType, Hetzner server type"""
    IMAGE = "image"
    """AWS imageId, Azure imageReference.sku, GCP imageId, Hetzner imageId"""
    AVAILABILITY_ZONE = "availability_zone"
    """AWS availabilityZone, Azure zone, GCP zone, Hetzner location"""
    REGION = "region"
    """AWS region, Azure location, GCP region, Hetzner location"""
    RESOURCE_GROUP = "resource_group"
    """AWS accountId, Azure resourceGroupName, GCP projectId, Hetzner projectId"""
    ACCOUNT = "account"
    """AWS accountId, Azure subscriptionId, GCP projectId, Hetzner projectId"""
    TAGS = "tags"
    """AWS tags, Azure tags, GCP labels, Hetzner labels"""
    USERDATA = "userdata"
    """The user-supplied data when creating the VM. Usually consumed by cloud-init"""

class ImdsProvider:
    http_timeout_seconds: int = 2
    params: dict[str, any] = {}

    def __init__(self, params: dict[str, any] = {}, http_timeout_seconds: int | None = None):
        self.params = params
        self.http_timeout_seconds = http_timeout_seconds if http_timeout_seconds is not None else 2

    def _http_request(self, method: str, url: str, headers: dict[str, str] | None = None) -> str:
        """Make a simple HTTP request to the given endpoint (stupidly simple wrapper around requests lib)."""
        import requests

        response = requests.request(method, url, headers=headers, timeout=self.http_timeout_seconds)
        if response.status_code == 200:
            return response.text

        raise requests.RequestException(f"Failed to get metadata at {url}: {response.status_code} {response.text}", response=response)

    def get_supported_informations(self) -> set[str]:
        """
        Returns the set of keys that are usable as "info" parameter in the query() method.
        Subclasses SHOULD also include (and MUST NOT override/redefine) those, returned by this method's base implementation.
        The returned keys are case-sensitive, yet no differently cased keys are allowed to be returned by subclasses.
        Subclasses SHOULD return uppercase-only keys that are usable for lookup into a subclass-provided enum class.

        Example: if a subclass wants to have a second "AVAILABILITY_ZONE" information,
        it must use a different name for it, not "availability_zone" or "AVAILABILITY_zone", but eg. "az", "az_id" or "zone".
        """
        return {info.name for info in CommonInformation}

    def query(self, info: str) -> any:
        """
        Query the IMDS for a specific piece of information.
        Recognizes the CommonInformation enum values and queries the IMDS for the corresponding information.
        If the info is not recognized, the returned result is implementation-dependant.

        Providers must raise NotImplementedError if the info is not recognized and thus cannot be queried from the IMDS.
        Providers may raise any other error if they tried to query the information, yet failed for any reason.
        """
        if info in CommonInformation.__members__:
            if info == CommonInformation.CLOUD_HOSTING_PROVIDER.name:
                return self.get_type().value
            elif info == CommonInformation.IMDS_VERSION.name:
                return self.get_protocol_version()
            elif info == CommonInformation.INSTANCE_ID.name:
                return self.get_instance_id()
            elif info == CommonInformation.INSTANCE_TYPE.name:
                return self.get_instance_type()
            elif info == CommonInformation.IMAGE.name:
                return self.get_image()
            elif info == CommonInformation.AVAILABILITY_ZONE.name:
                return self.get_availability_zone()
            elif info == CommonInformation.REGION.name:
                return self.get_region()
            elif info == CommonInformation.RESOURCE_GROUP.name:
                return self.get_resource_group()
            elif info == CommonInformation.ACCOUNT.name:
                return self.get_account()
            elif info == CommonInformation.TAGS.name:
                return self.get_tags()
            elif info == CommonInformation.USERDATA.name:
                return self.get_userdata()

        raise NotImplementedError(f"Base class ImdsProvider only supports CommonInformation, not \"{info}\".")

    @abstractmethod
    def detect(self) -> bool:
        """
        Detects if the current host is likely running on this cloud hosting provider.
        Returns True if it most-likely is, False otherwise.
        """
        pass

    @abstractmethod
    def get_type(self) -> CloudHostingProviderType:
        """Returns the cloud provider type."""
        pass

    @abstractmethod
    def get_instance_id(self) -> str:
        """
        Return the VM instance ID of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "i-1234567890abcdef0", Azure "12345678-1234-1234-1234-1234567890ab", GCP "1234567890123456789", Hetzner "123456"
        """
        pass

    @abstractmethod
    def get_instance_type(self) -> str:
        """
        Returns the VM instance type of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "t2.micro", Azure "Standard_B1s", GCP "e2-micro", Hetzner "cx11"
        """
        pass

    @abstractmethod
    def get_image(self) -> str:
        """
        Returns the VM image ID of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "ami-1234567890abcdef0", Azure "Canonical:UbuntuServer:18.04-LTS:latest", GCP "projects/ubuntu-os-cloud/global/images/ubuntu-1804-bionic-v20210429", Hetzner "ubuntu-20.04"
        """
        pass

    @abstractmethod
    def get_availability_zone(self) -> str:
        """
        Returns only the availability zone name/ID of the instance in the native naming schema of the cloud hosting provider.
        Will automatically remove possible region prefixes that some providers natively have (eg. AWS would return "eu-central-1a" instead of just "a", so this gets normalized here).
        Examples: AWS "a", Azure "1", GCP "b", Hetzner "1"
        """
        pass

    @abstractmethod
    def get_region(self) -> str:
        """
        Returns the region name of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "eu-central-1", Azure "westeurope", GCP "europe-west1", Hetzner "nbg1"
        """
        pass

    @abstractmethod
    def get_resource_group(self) -> str:
        """
        Returns the resource group name of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "123456789012" (AWS does not have that: it is the same as the accountId), Azure "my-resource-group", GCP "my-project-id", Hetzner "my-project-id"
        """
        pass

    @abstractmethod
    def get_account(self) -> str:
        """
        Returns the account ID of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS "123456789012", Azure "12345678-1234-1234-1234-1234567890ab", GCP "my-project-id", Hetzner "my-project-id"
        """
        pass

    @abstractmethod
    def get_tags(self) -> dict[str, str]:
        """
        Returns the tags of the instance in the native naming schema of the cloud hosting provider.
        Examples: AWS {"Name": "my-instance", "Environment": "production"}, Azure {"Name": "my-instance", "Environment": "production"}, GCP {"Name": "my-instance", "Environment": "production"}, Hetzner {"Name": "my-instance", "Environment": "production"}
        """
        pass

    @abstractmethod
    def get_userdata(self) -> str | None:
        """
        Returns the base64-encoded userdata of the instance.
        This is oftentimes consumed by cloud-init.
        Base64-encoding is applied to support binary contents.
        Base64-encoding uses the URL-safe variant (characters a-z, A-Z, 0-9, "-" and "_").
        """
        pass

    @abstractmethod
    def get_protocol_version(self) -> str:
        """Returns the IMDS version."""
        pass
