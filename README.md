# Ansible collection "imds"

The `instance metadata service` (IMDS) is a nonstandard way that cloud hosting providers (CHP, eg. AWS, Azure, Google Cloud, Alibaba, Lidl, Hetzner) expose infrastructure-related information to VMs.
It is usually a HTTP/REST-ful API at a well-known, non-routable IP address that is local to the VM.

Since IMDS is not standardized in any way, it is more a "generally quite common idea" rather than a protocol.
This makes it cumbersome for ansible plays to query information from it.
Yet that would oftentimes be helpful, in order to decouple between "CHP-related infrastructure" (commonly configured via OpenTofu)
and "VM provisioning" (commonly done via Ansible).

This collections provides facilities to interact with IMDS in a mostly-standardized way.
Common operations that nearly all of today's major CHPs implement, are abstracted and offered in a CHP-agnostic way.
