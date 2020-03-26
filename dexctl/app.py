import click
import json
import subprocess
import typing

import yaml

from .client import DexClient, DexServerConfig


class K8sObjectRef:
    name: typing.AnyStr = None
    namespace: typing.AnyStr = None

    def __init__(self, namespace, name):
        self.namespace = namespace
        self.name = name


class DexCtlOAuthClientOptions:
    oauth_client: DexClient.OAuth2Client = None

    def __init__(self, oauth_client):
        self.oauth_client = DexClient.OAuth2Client(**oauth_client)


class DexCtlCreateClientOptions(DexCtlOAuthClientOptions):
    pass


class DexCtlDeleteClientOptions(DexCtlOAuthClientOptions):
    pass


class DexCtlSecretOptions:
    secret_ref: K8sObjectRef = None
    oauth_client_ref: K8sObjectRef = None
    secret_key_client_id: typing.AnyStr = "client_id"
    secret_key_client_secret: typing.AnyStr = "client_secret"

    def __init__(self, oauth_client_ref, secret_ref):
        self.oauth_client_ref = oauth_client_ref
        self.secret_ref = secret_ref


class DexCtlCreateSecretOptions(DexCtlSecretOptions):
    pass


class DexCtlDeleteSecretOptions(DexCtlSecretOptions):
    pass


class DexCtlApp:
    server_config: DexServerConfig = None

    _client = None

    def __init__(self, server_config: DexServerConfig):
        self.server_config = server_config

    @property
    def client(self) -> DexClient:
        if self._client is None:
            self._client = self.server_config.create_dex_client()
        return self._client

    def check_connection(self):
        version_resp = self.client.GetVersion()
        click.echo(
            f"info: Connected to {self.server_config.dex_address}: {version_resp!r}",
            err=True,
        )

    def _kubectl(
        self,
        cmd: typing.List,
        namespace: typing.AnyStr = None,
        input: typing.IO = None,
    ) -> typing.Mapping:
        cmd = list(cmd)
        cmd.extend(["-o", "yaml"])
        return yaml.safe_load(self._kubectl_str(cmd, namespace=namespace, input=input))

    def _kubectl_str(
        self,
        cmd: typing.List,
        namespace: typing.AnyStr = None,
        input: typing.IO = None,
    ) -> typing.AnyStr:

        cmd = list(cmd)
        cmd.insert(0, "kubectl")

        if namespace is not None and "-n" not in cmd:
            cmd.extend(["-n", namespace])

        proc = subprocess.run(cmd, input=input, capture_output=True)
        try:
            proc.check_returncode()
        except:
            print(proc.stderr.decode("utf8"))
            raise

        return proc.stdout

    def _get_oauth2client(self, ref: K8sObjectRef) -> DexClient.OAuth2Client:
        our_namespace = ref.namespace

        if our_namespace is None:
            our_namespace = self._kubectl_str(
                ["config", "view", "--minify", "-o", "jsonpath={..namespace}"]
            )

        # Dex generates a new k8s name with some hashing function that is
        # not duplicable as far as I can tell, so get all oauth2clients and
        # find out which one is ours.
        all_clients = self._kubectl(["get", "oauth2clients"], namespace=our_namespace)
        for oauth_client in all_clients["items"]:
            if oauth_client["id"] == ref.name:
                return DexClient.oauth2client_from_k8s(oauth_client)

        raise Exception(
            f"Could not find OAuth2Client in namespace='{our_namespace}' with id='{ref.name}'"
        )

    def do_create_client(self, opts: DexCtlCreateClientOptions):
        resp = self.client.CreateClient(client=opts.oauth_client)
        if resp.already_exists:
            resp.client.id = opts.oauth_client.id
            click.echo(
                f"info: Dex OAuth2Client {resp.client.id} already exists.", err=True,
            )
        else:
            click.echo(
                f"info: Dex OAuth2Client {resp.client.id} created.", err=True,
            )
        return resp

    def do_create_secret(self, opts: DexCtlCreateSecretOptions):
        if opts.secret_ref.name is None:
            click.echo("info: No secret specified to create, skipping...", err=True)
            return

        our_client = self._get_oauth2client(opts.oauth_client_ref)

        name = opts.secret_ref.name
        namespace = opts.secret_ref.namespace
        existing_secret = None
        try:
            existing_secret = self._kubectl(
                ["get", "secret", name], namespace=namespace
            )
        except subprocess.CalledProcessError as exc:
            if b"(NotFound)" not in exc.stderr:
                raise

        if existing_secret is None:
            click.echo(
                f"info: secret {namespace}/{name} does not exist, creating...", err=True
            )
            existing_secret = self._kubectl(
                ["create", "secret", "generic", name], namespace=namespace
            )
            if existing_secret:
                click.echo(f"info: secret {namespace}/{name} created", err=True)
            else:
                click.echo(
                    f"err: failed to create secret {namespace}/{name}."
                    "dexctl cannot resolve this problem, please investigate kubernetes state!",
                    err=True,
                )
                return False

        patch = dict(
            stringData={
                opts.secret_key_client_id: our_client.id,
                opts.secret_key_client_secret: our_client.secret,
            }
        )

        self._kubectl_str(
            ["patch", "secret", name, "-p", yaml.dump(patch).encode("utf8")],
            namespace=namespace,
        )

        click.echo(
            f"info: secret {namespace}/{name} updated with OAuth client_id and client_secret",
            err=True,
        )

    def do_delete_client(self, opts: DexCtlDeleteClientOptions):
        return self.client.DeleteClient(id=opts.oauth_client.id)

    def do_delete_secret(self, opts: DexCtlDeleteSecretOptions):
        if opts.secret_ref.name is None:
            click.echo("info: No secret specified to delete, skipping...", err=True)
            return

        name = opts.secret_ref.name
        namespace = opts.secret_ref.namespace
        key_client_id = opts.secret_key_client_id
        key_client_secret = opts.secret_key_client_secret

        existing_secret = None
        try:
            existing_secret = self._kubectl(
                ["get", "secret", name], namespace=namespace
            )
        except subprocess.CalledProcessError as exc:
            if b"(NotFound)" not in exc.stderr:
                raise

        if existing_secret is None:
            click.echo(
                f"info: secret {namespace}/{name} does not exist, nothing to delete",
                err=True,
            )
        elif set(existing_secret.get("data", {}).keys()) - set(
            (key_client_id, key_client_secret)
        ):
            click.echo(
                f"info: secret {namespace}/{name} exists and has unknown keys. "
                f"Removing {key_client_id} and {key_client_secret}.",
                err=True,
            )

            patch = []
            if key_client_id in existing_secret.get("data", {}):
                patch.append(dict(op="remove", path=f"/data/{key_client_id}"))
            if key_client_secret in existing_secret.get("data", {}):
                patch.append(dict(op="remove", path=f"/data/{key_client_secret}"))

            self._kubectl(
                [
                    "patch",
                    "secret",
                    name,
                    "--type",
                    "json",
                    "-p",
                    json.dumps(patch).encode("utf8"),
                ],
                namespace=namespace,
            )
            click.echo(
                f"info: secret {namespace}/{name}: "
                f"removed {key_client_id} and {key_client_secret}, if they existed.",
                err=True,
            )
        else:
            click.echo(f"info: secret {namespace}/{name} deleting...", err=True)
            self._kubectl_str(["delete", "secret", name], namespace)
            click.echo(
                f"info: secret {namespace}/{name} removed keys {key_client_id} and {key_client_secret}.",
                err=True,
            )
