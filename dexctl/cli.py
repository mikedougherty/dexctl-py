import collections
import functools
import json
import os
import sys
import subprocess
import typing

import grpc
import click
import yaml

from . import app
from . import client

option = functools.partial(click.option, show_default=True)


class ClickOptions:
    dex_address = option(
        "--dex-address",
        default=client.DexServerConfig.dex_address,
        envvar="DEX_ADDR",
        show_envvar=True,
        help="Address of dex server in the format 'host:port'",
        type=click.STRING,
    )

    ca_cert = option(
        "--ca-cert",
        default="ca.crt",
        help="Path to ca.crt file",
        type=click.File("rb"),
    )

    tls_cert = option(
        "--tls-cert",
        default="tls.crt",
        help="Path to tls.crt file",
        type=click.File("rb"),
    )

    tls_key = option(
        "--tls-key",
        default="tls.key",
        help="Path to tls.key file",
        type=click.File("rb"),
    )

    namespace = option(
        "--namespace",
        "-n",
        default=None,
        help="k8s namespace of dex server. if unset, uses kubectl context",
        type=click.STRING,
    )

    secret_name = option(
        "--secret-name",
        default=None,
        help="Secret to create with OAuth Client configuration. If unset, does not create a secret",
        type=click.STRING,
    )

    secret_namespace = option(
        "--secret-namespace",
        default=None,
        help="Namespace for secret creation. If unset, uses same as '-n'",
        type=click.STRING,
    )

    client_definition = click.option(
        "--file",
        "-f",
        "client_definition",
        default="-",
        show_default="stdin",
        help=(
            "Path to OAuth2Client definition, a yaml file with properties as specified here: "
            "https://github.com/dexidp/dex/blob/master/api/api.proto#L7-L15"
        ),
        type=click.File("r"),
    )


@click.group()
@ClickOptions.dex_address
@ClickOptions.ca_cert
@ClickOptions.tls_cert
@ClickOptions.tls_key
@click.pass_context
def cli(
    ctx: click.Context = None,
    ca_cert: typing.BinaryIO = None,
    tls_cert: typing.BinaryIO = None,
    tls_key: typing.BinaryIO = None,
    dex_address: typing.AnyStr = None,
):
    ctx.obj = app.DexCtlApp(
        client.DexServerConfig(ca_cert, tls_cert, tls_key, dex_address)
    )


@cli.command()
@ClickOptions.namespace
@ClickOptions.secret_name
@ClickOptions.secret_namespace
@ClickOptions.client_definition
@click.pass_context
def create(
    ctx: click.Context,
    namespace: typing.AnyStr,
    secret_name: typing.AnyStr,
    secret_namespace: typing.AnyStr,
    client_definition: typing.TextIO,
):
    if ctx.obj is None:
        raise Exception("No dex client application configured")

    ctx.obj.check_connection()

    create_response = ctx.obj.do_create_client(
        app.DexCtlCreateClientOptions(yaml.safe_load(client_definition))
    )

    ctx.obj.do_create_secret(
        app.DexCtlCreateSecretOptions(
            app.K8sObjectRef(namespace, create_response.client.id),
            app.K8sObjectRef(secret_namespace or namespace, secret_name),
        )
    )

    # TODO: make sure create is successful


@cli.command()
@ClickOptions.client_definition
@ClickOptions.namespace
@ClickOptions.secret_name
@ClickOptions.secret_namespace
@click.pass_context
def delete(
    ctx: click.Context,
    namespace: typing.AnyStr,
    secret_name: typing.AnyStr,
    secret_namespace: typing.AnyStr,
    client_definition: typing.TextIO,
):
    if ctx.obj is None:
        raise Exception("No dex client application configured")

    ctx.obj.check_connection()
    delete_opts = app.DexCtlDeleteClientOptions(yaml.safe_load(client_definition))

    ctx.obj.do_delete_secret(
        app.DexCtlDeleteSecretOptions(
            app.K8sObjectRef(namespace, delete_opts.oauth_client.id),
            app.K8sObjectRef(secret_namespace or namespace, secret_name),
        )
    )

    delete_response = ctx.obj.do_delete_client(delete_opts)

    if delete_response.not_found:
        click.echo(
            f"err: Dex reported OAuth2Client {delete_opts.oauth_client.id} did not exist.",
            err=True,
        )
        return False
    else:
        click.echo(f"success: OAuth2Client {delete_opts.oauth_client.id} deleted.")
        return True


if __name__ == "__main__":
    cli()
