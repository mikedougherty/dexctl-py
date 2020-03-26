from . import api_pb2
from . import api_pb2_grpc

from .api_pb2 import *
from .api_pb2_grpc import (
    DexStub,
    DexServicer as _DexServicer,
    add_DexServicer_to_server,
)


class DexServicer(_DexServicer):
    def add_to_server(self, server):
        return add_DexServicer_to_server(self, server)


__all__ = ["DexStub", "DexServicer"]
