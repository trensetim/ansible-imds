# Ansible collection "imds"

The `instance metadata service` (IMDS) is a nonstandard way that cloud hosting providers (CHP, eg. AWS, Azure, Google Cloud, Alibaba, Lidl, Hetzner) expose infrastructure-related information to VMs.
It is usually a HTTP/REST-ful API at a well-known, non-routable IP address that is local to the VM.

Since IMDS is not standardized in any way, it is more a "generally quite common idea" rather than a protocol.
This makes it cumbersome for ansible plays to query information from it.
Yet that would oftentimes be helpful, in order to decouple between "CHP-related infrastructure" (commonly configured via OpenTofu)
and "VM provisioning" (commonly done via Ansible).

This collections provides facilities to interact with IMDS in a mostly-standardized way.
Common operations that nearly all of today's major CHPs implement, are abstracted and offered in a CHP-agnostic way.

As of today, there is just one module `imds_facts`, which queries for requested information.

# The `imds_facts` module

## Synopsis / Usage Example:

```yaml
tasks:
    - name: Gather imds facts
      timtrense.imds.imds_facts:
          provider: aws # or auto, azure, gcp, hetzner
          query: # hint: can also be just a single string
              - common # alias for "all CHP-agnostic information"
              - reservation_id # an AWS-native information
          allow_failed_queries: # which information is not necessarily mandatory
              - reservation_id
              - tags # comes from "common"; on AWS access to tag metadata is restricted by default
```

## Parameters

| Param                  | Default     | Explanation                                                           |
| ---------------------- | ----------- | --------------------------------------------------------------------- |
| `provider`             | `auto`      | Which strategy to use for communicating with the IMDS of the instance |
| `query`                | `common`    | Which information to extract from IMDS                                |
| `allow_failed_queries` | `[]` = none | Which queries are optional and failures are swallowed                 |
| `http_timeout_seconds` | `0.5`       | The applied request timeout                                           |
| `provider_params`      | `{}`        | Allows passing parameters to the selected provider                    |

The following values work for `queries`:

- `common` (alias): extracts all provider-agnostic information.
- `all` (alias): extracts all information the selected provider has to offer.
- `xyz`: extracts exactly the `xyz` field, no matter whether it is provider-agnostic or -specific.

## Extracted facts

| Info                           | CHP-Format | Details                                                                                                                                                                                                      |
| ------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `imds_cloud_hosting_provider`  | agnostic   | The normalized form of the CHP: `amazon`, `azure`, `google`, `hetzner`.                                                                                                                                      |
| `imds_version`                 | specific   | The version number of IMDS protocol in use. For `amazon` that is either `"1"` or `"2"`. For `azure` it is the `api-version`.                                                                                 |
| `imds_instance_id`             | specific   | The ID of the VM.                                                                                                                                                                                            |
| `imds_instance_type`           | specific   | The size/type of the VM.                                                                                                                                                                                     |
| `imds_image`                   | specific   | The disk image used for spawning the VM originally.                                                                                                                                                          |
| `imds_availability_zone`       | specific   | The AZ inside the region.                                                                                                                                                                                    |
| `imds_region`                  | specific   | The geographical region of the datacenter cluster.                                                                                                                                                           |
| `imds_resource_group`          | specific   | For AWS same as `account`. For Azure: Resource Group ID.                                                                                                                                                     |
| `imds_account`                 | specific   | The name or ID of the owning tenant of the VM. (Not necessarily a root-account).                                                                                                                             |
| `imds_tags`                    | agnostic   | A plain key-value map. If any CHP does not support values for labels/tags/annotations, the keys will be present with `""` (empty-string) values.                                                             |
| `imds_userdata`                | agnostic   | A plain-text (or `null`). The [userdata feature](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) of most CHPs. Will be `urlsafe base64` encoded (`a-zA-Z0-9_-`, to support binary data). |
| `aws_account_id`               | AWS-only   | Same as `account`.                                                                                                                                                                                           |
| `aws_architecture`             | AWS-only   | CPU ISA                                                                                                                                                                                                      |
| `aws_reservation_id`           | AWS-only   | The instance savings plan.                                                                                                                                                                                   |
| `aws_security_groups`          | AWS-only   | The network security groups.                                                                                                                                                                                 |
| `aws_az_id`                    | AWS-only   | The availability zone ID.                                                                                                                                                                                    |
| `aws_az`                       | AWS-only   | The availability zone name without normalizations (eg. `eu-central-1a`). I.e. region+zone.                                                                                                                   |
| `aws_profile`                  | AWS-only   | The used hypervisor type (eg. `default_hvm`).                                                                                                                                                                |
| `aws_system`                   | AWS-only   | The used hypervisor type (eg. `nitro`).                                                                                                                                                                      |
| `aws_hibernation_configured`   | AWS-only   | Whether hibernation is enabled.                                                                                                                                                                              |
| `aws_block_device_mapping_ami` | AWS-only   | To which block device the AMI is mounted.                                                                                                                                                                    |
| `aws_...`                      | AWS-only   | Various other information. See [aws.py](./src/main/ansible-galaxy/ansible_collections/timtrense/imds/plugins/module_utils/aws.py)                                                                            |
| `az_physical_zone`             | Azure-only | [Physical Zone](https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview?tabs=azure-cli#physical-and-logical-availability-zones)                                                      |
| `az_logical_zone`              | Azure-only | [Logical Zone](https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview?tabs=azure-cli#physical-and-logical-availability-zones)                                                       |
| `az_placement_group_id`        | Azure-only | [Placement Group](https://learn.microsoft.com/en-us/azure/virtual-machines/co-location)                                                                                                                      |
| `az_priority`                  | Azure-only | Spot-VM priority.                                                                                                                                                                                            |
| `az_eviction_policy`           | Azure-only | Spot-VM eviction policy.                                                                                                                                                                                     |
| `az_subscription_id`           | Azure-only | Matches `account`.                                                                                                                                                                                           |
| `az_scale_set_name`            | Azure-only | Name of the scale set.                                                                                                                                                                                       |
| `az_publisher`                 | Azure-only | Part of the `imds_image`.                                                                                                                                                                                    |
| `az_sku`                       | Azure-only | Part of the `imds_image`.                                                                                                                                                                                    |
| `az_version`                   | Azure-only | Part of the `imds_image`. It is synthesized as `publisher:sku:version`.                                                                                                                                      |
| `az_...`                       | Azure-only | Various other information. See [az.py](./src/main/ansible-galaxy/ansible_collections/timtrense/imds/plugins/module_utils/azure.py)                                                                           |

While **most** information yields strings, the information is actually parsed into proper types, as much as possible.

CHP-Formats:

- `agnostic`: The contained values will be strictly specified by this module and do not change format across CHPs
- `specific`: The CHP-native representation is used.
- `xy-only`: This field only exists for CHP `xy`

# Notes about supported Providers

- `aws`:
    - `IMDSv2` is also supported automatically (and preferred, using `v1` only as fallback).
    - The native-format of the availability zone (eg. `eu-central-1a`) is split into `imds_region` and `imds_availability_zone` (eg. `eu-central-1`+`a`)
- `azure`:
    - The `imds_image` is synthesized as `publisher:sku:version`.

The `provider_params` names are prefixed with the provider name, such that auto-detection does not yield conflicts in multicloud scenarios.

# Note on TLS

All known providers only support plain-http (ie. without TLS-encryption).
Thus, the reported information is vulnerable to man-in-the-middle (MITM) attacks by malware _that is already running on the remote host at the time the ansible playbook runs_.
Since the IMDS-endpoint is hosted on a non-routed, host-local IP address, remote tampering is ruled out.
So actually the attack vector is rather small: the remote would need to be compromised at root level, for a MITM to work.

Users of _IMDS in general_ should consider, whether that is a realistic attack scenario for them.
