'''
The MIT License (MIT)
Copyright (c) 2019 - Naoyuki Tai
'''

__all__ = ['GUID_STR', 'OPCODE', 'STATUS', 'HANDSHAKE', 'FAILED_HANDSHAKE']

# Not a random GUID
GUID_STR = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

# RFC 6455 opcodes
class OPCODE:
  STREAM = 0x0
  TEXT = 0x1
  BINARY = 0x2
  CLOSE = 0x8
  PING = 0x9
  PONG = 0xA
  pass


# 11.7.  WebSocket Close Code Number Registry

class STATUS:
  Normal_Closure = 1000
  Going_Away = 1001
  Protocol_error = 1002
  Unsupported_Data = 1003
  Reserved_1004 = 1004
  No_Status_Rcvd = 1005
  Abnormal_Closure = 1006
  Invalid_frame_payload_data = 1007
  Policy_Violation = 1008
  Message_Too_Big  = 1009
  Mandatory_Ext  = 1010
  Internal_Server_Error = 1011
  TLS_handshak = 1015

  REGISTRY = {
    1000: ('Normal Closure'),
    1001: ('Going Away'),
    1002: ('Protocol error'),
    1003: ('Unsupported Data'),
    1004: ('---Reserved----'),
    1005: ('No Status Rcvd'),
    1006: ('Abnormal Closure'),
    1007: ('Invalid frame payload data'),
    1008: ('Policy Violation'),
    1009: ('Message Too Big '),
    1010: ('Mandatory Ext. '),
    1011: ('Internal Server Error'),
    1015: ('TLS handshake')
  };
  pass


HANDSHAKE = (
  "HTTP/1.1 101 Switching Protocols\r\n"
  "Upgrade: WebSocket\r\n"
  "Connection: Upgrade\r\n"
  "Sec-WebSocket-Accept: %(acceptstr)s\r\n\r\n"
)

FAILED_HANDSHAKE = (
  "HTTP/1.1 426 Upgrade Required\r\n"
  "Upgrade: WebSocket\r\n"
  "Connection: Upgrade\r\n"
  "Sec-WebSocket-Version: 13\r\n"
  "Content-Type: text/plain\r\n\r\n"
  "This service requires use of the WebSocket protocol\r\n"
)
