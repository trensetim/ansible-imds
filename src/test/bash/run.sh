#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
cd ../ansible

if [ -n "${ANSIBLE_VAULT_PASSWORD_FILE+x}" ]; then
    unset ANSIBLE_VAULT_PASSWORD_FILE
fi

ansible-playbook -i inventory.yml test.playbook.yml

