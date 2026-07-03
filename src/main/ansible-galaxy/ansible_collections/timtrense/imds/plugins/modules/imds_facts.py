#!/usr/bin/python
# -*- coding: utf-8 -*-

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.timtrense.imds.plugins.module_utils.imds_provider import CommonInformation, ImdsProvider
from ansible_collections.timtrense.imds.plugins.module_utils.aws import AwsProvider

MODULE = AnsibleModule(
    argument_spec={
        "provider": {
            "type": "str",
            "required": False,
            "choices": ['auto', 'amazon', 'azure', 'google', 'hetzner', 'aws', 'az', 'azure', 'gcp', 'hz'],
            "default": 'auto'
        },
        "query": {
            "type": "list",
            "elements": "str",
            "required": False,
            "default": [] # empty means everything
        },
        "allow_failed_queries": {
            "type": "list",
            "elements": "str",
            "required": False,
            "default": [] # empty means nothing is allowed to fail
        },
        "http_timeout_seconds": {
            "type": "float",
            "required": False,
            "default": 0.5
        }
    },
    supports_check_mode=True
)

def parse_requested_info(provider: ImdsProvider) -> set[str]:
    requested_info: list[str] | str = MODULE.params["query"]
    if isinstance(requested_info, str):
        requested_info = [requested_info]

    for info in requested_info:
        if info == "common":
            requested_info.remove(info)
            requested_info.extend([info.name for info in CommonInformation])
        if info == "all" or info == "*":
            requested_info = [] # make empty --> means "all"
            break

    if requested_info == []:
        requested_info = list(provider.get_supported_informations())

    requested_info = set(requested_info)
    requested_info = {info.upper() for info in requested_info}

    return requested_info

def parse_allowed_fails(provider: ImdsProvider) -> set[str]:
    allowed_fails: list[str] | str = MODULE.params["allow_failed_queries"]

    if isinstance(allowed_fails, str):
        allowed_fails = [allowed_fails]

    for info in allowed_fails:
        if info == "common":
            allowed_fails.remove(info)
            allowed_fails.extend([info.name for info in CommonInformation])
        if info == "all" or info == "*":
            allowed_fails = provider.get_supported_informations()
            break
        if info == "none":
            allowed_fails = []
            break

    allowed_fails = set(allowed_fails)
    allowed_fails = {info.upper() for info in allowed_fails}

    return allowed_fails

if __name__ == '__main__':
    result = {
        "changed": False,
        "ansible_facts": {}
    }

    requested_provider: str = MODULE.params["provider"].lower()
    provider: ImdsProvider

    if requested_provider == "auto":
        MODULE.fail_json(msg=f"Provider autodetection is not supported yet", **result) # TODO
    elif requested_provider == "aws" or requested_provider == "amazon":
        provider = AwsProvider()
    else:
        MODULE.fail_json(msg=f"Provider {requested_provider} is not supported yet", **result) # TODO Azure, Hetzner, GCP

    provider.http_timeout_seconds = MODULE.params["http_timeout_seconds"]

    requested_info = parse_requested_info(provider)
    allowed_fails = parse_allowed_fails(provider)
    for info in requested_info:
        key = (
            f"imds_{CommonInformation[info].name.lower()}"
            if info in CommonInformation.__members__
            else f"imds_{provider.get_type().name.lower()}_{info.lower()}"
        )
        try:
            result["ansible_facts"][key] = provider.query(info)
        except Exception as e:
            if info in allowed_fails:
                fallback_value = None
                if info == CommonInformation.TAGS.name:
                    fallback_value = {}
                result["ansible_facts"][key] = fallback_value
            else:
                MODULE.fail_json(msg=f"Failed to query information \"{info}\": {e}", **result)

    MODULE.exit_json(**result)
