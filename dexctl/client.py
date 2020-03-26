import typing

import grpc

from .pb import DexStub
from .pb import api_pb2


class DexClient:
    OAuth2Client = api_pb2.Client

    def __init__(self, channel):
        self.stub = DexStub(channel)

    def GetVersion(self) -> api_pb2.VersionResp:
        return self.stub.GetVersion(api_pb2.VersionReq())

    def CreateClient(self, **kwargs) -> api_pb2.CreateClientResp:
        return self.stub.CreateClient(api_pb2.CreateClientReq(**kwargs))

    def DeleteClient(self, **kwargs) -> api_pb2.DeleteClientResp:
        return self.stub.DeleteClient(api_pb2.DeleteClientReq(**kwargs))

    @classmethod
    def oauth2client_from_k8s(cls, obj: typing.Mapping) -> api_pb2.Client:
        keep_keys = set(cls.OAuth2Client.DESCRIPTOR.fields_by_name.keys())
        for key in list(obj.keys()):
            if key not in keep_keys:
                obj.pop(key)

        return cls.OAuth2Client(**obj)


class TLSConfig:
    ca_cert: typing.ByteString = None
    tls_cert: typing.ByteString = None
    tls_key: typing.ByteString = None

    def __init__(
        self,
        ca_cert: typing.BinaryIO,
        tls_cert: typing.BinaryIO,
        tls_key: typing.BinaryIO,
    ):
        self.ca_cert = ca_cert.read()
        self.tls_cert = tls_cert.read()
        self.tls_key = tls_key.read()


class DexServerConfig:
    """
    Common variables for connecting to dex
    """

    tls_config: TLSConfig = None
    dex_address: typing.AnyStr = "localhost:5000"

    def __init__(
        self,
        ca_cert: typing.BinaryIO,
        tls_cert: typing.BinaryIO,
        tls_key: typing.BinaryIO,
        dex_address: typing.AnyStr,
    ):
        self.tls_config = TLSConfig(ca_cert, tls_cert, tls_key)
        self.dex_address = dex_address

    def create_dex_client(self) -> DexClient:
        creds = grpc.ssl_channel_credentials(
            self.tls_config.ca_cert, self.tls_config.tls_key, self.tls_config.tls_cert
        )

        return DexClient(grpc.secure_channel(self.dex_address, creds))
