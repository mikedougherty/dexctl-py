# dexctl-py
Python client for dexidp/dex

# Requirements
- Python3
- Activated virtualenv for the project (e.g. `virtualenv -p python3 venv; . venv/bin/activate`)
- Kubernetes config/context configured such that e.g. `kubectl get secret` works.
- Dex (https://github.com/dexidp/dex) up and running and gRPC port accessible from your host.
- gRPC certs for Dex on your filesystem (recommended paths: ca.crt, tls.crt, tls.key)

# Setup/Hack
1. `pip install -r requirements.txt`
1. `export PYTHONPATH=.`
1. `bin/dexctl --help`

# Future development
1. Tests!
1. Allow fetching gRPC TLS from k8s
1. Allow changing keys within the target secret where client ID and secret are stored
1. More docs
1. Package/publish?
