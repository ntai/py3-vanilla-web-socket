#!/usr/bin/env python3
'''
The MIT License (MIT)
Copyright (c) 2019 - Naoyuki Tai

The MIT License (MIT)
Copyright (c) 2013 Dave P.
'''

#
# This only works with Python3
#

import sys
import socketserver
from http.server import BaseHTTPRequestHandler
from io import StringIO, BytesIO

import hashlib, base64, socket, struct, errno, codecs
from collections import deque
from select import select
import signal
import rfc6455
import logging
import ssl
from optparse import OptionParser

__all__ = ['WebSocketConnection', 'VanillaWebSocketServer', 'VanillaSSLWebSocketServer' ]


def is_unicode(val):
  return isinstance(val, str)

class HTTPRequest(BaseHTTPRequestHandler):
  def __init__(self, request_text):
    self.rfile = BytesIO(request_text)
    self.raw_requestline = self.rfile.readline()
    self.error_code = self.error_message = None
    self.parse_request()
    pass
  pass

MAXHEADER = 65536
MAXPAYLOAD = 33554432

class WebSocketConnection(object):
  def __init__(self, server, sock, address):
    self.server = server
    self.client = sock
    self.address = address

    self.handshaked = False
    self.headerbuffer = bytearray()
    self.headertoread = 2048

    self.fin = 0
    self.data = bytearray()
    self.opcode = 0
    self.hasmask = 0
    self.maskarray = None
    self.length = 0
    self.lengtharray = None
    self.index = 0
    self.request = None
    self.usingssl = False

    self.frag_start = False
    self.frag_type = rfc6455.OPCODE.BINARY
    self.frag_buffer = None
    self.frag_decoder = codecs.getincrementaldecoder('utf-8')(errors='strict')
    self.closed = False
    self.sendq = deque()
    
    self.state = self._STATE_HEADER_FIRSTBYTE

    # restrict the size of header and payload for security reasons
    self.maxheader = MAXHEADER
    self.maxpayload = MAXPAYLOAD
    pass

  def handleMessage(self):
    """
    Called when websocket frame is received.
    To access the frame data call self.data.
    If the frame is Text then self.data is a unicode object.
    If the frame is Binary then self.data is a bytearray object.
    """
    pass

  def handleConnected(self):
    """
    Called when a websocket client connects to the server.
    """
    pass

  def handleClose(self):
     """
     Called when a websocket server gets a Close frame from a client.
     """
     pass

  def _handleClosePacket(self):
    status = rfc6455.STATUS.Normal_Closure
    reason = u''
    length = len(self.data)

    if length == 0:
      pass
    elif length >= 2:
      status = struct.unpack_from('!H', self.data[:2])[0]
      reason = self.data[2:]

      if not rfc6455.STATUS.REGISTRY.get(status):
        status = rfc6455.STATUS.Going_Away
        pass

      if len(reason) > 0:
        try:
          reason = reason.decode('utf8', errors='strict')
        except Exception as exc:
          print("close packet: " + str(exc))
          status = rfc6455.STATUS.Going_Away
          pass
        pass
      pass
    else:
      status = rfc6455.STATUS.Going_Away
      pass
    self.close(status, reason)
    pass

  # Do this if it's not fin packet
  def _handleFragmentPacket(self):
    if self.opcode != rfc6455.OPCODE.STREAM:
      if self.opcode == rfc6455.OPCODE.PING or self.opcode == rfc6455.OPCODE.PONG:
        raise Exception('control messages can not be fragmented')

      self.frag_type = self.opcode
      self.frag_start = True
      self.frag_decoder.reset()

      if self.frag_type == rfc6455.OPCODE.TEXT:
        self.frag_buffer = []
        utf_str = self.frag_decoder.decode(self.data, final = False)
        if utf_str:
          self.frag_buffer.append(utf_str)
          pass
        pass
      else:
        self.frag_buffer = bytearray()
        self.frag_buffer.extend(self.data)
        pass
      pass

    else:
      if self.frag_start is False:
        raise Exception('fragmentation protocol error')

      if self.frag_type == rfc6455.OPCODE.TEXT:
        utf_str = self.frag_decoder.decode(self.data, final = False)
        if utf_str:
          self.frag_buffer.append(utf_str)
          pass
        pass
      else:
        self.frag_buffer.extend(self.data)
        pass
      pass
    pass
    
  def _handleCompletePacket(self):
    if self.opcode == rfc6455.OPCODE.STREAM:
      if self.frag_start is False:
        raise Exception('fragmentation protocol error')

      if self.frag_type == rfc6455.OPCODE.TEXT:
        utf_str = self.frag_decoder.decode(self.data, final = True)
        self.frag_buffer.append(utf_str)
        self.data = u''.join(self.frag_buffer)
        pass
      else:
        self.frag_buffer.extend(self.data)
        self.data = self.frag_buffer
        pass

      self.handleMessage()

      self.frag_decoder.reset()
      self.frag_type = rfc6455.OPCODE.BINARY
      self.frag_start = False
      self.frag_buffer = None
      pass

    elif self.opcode == rfc6455.OPCODE.PING:
      self._sendMessage(False, rfc6455.OPCODE.PONG, self.data)
      pass

    elif self.opcode == rfc6455.OPCODE.PONG:
      pass

    else:
      if self.frag_start is True:
        raise Exception('fragmentation protocol error')

      if self.opcode == rfc6455.OPCODE.TEXT:
        try:
          self.data = self.data.decode('utf8', errors='strict')
        except Exception as exc:
          print(str(exc))
          raise Exception('invalid utf-8 payload')
        pass

      self.handleMessage()
      pass
    pass

  def _handlePacket(self):
    if self.opcode == rfc6455.OPCODE.CLOSE:
      self._handleClosePacket()
      return
    elif self.opcode == rfc6455.OPCODE.STREAM:
      pass
    elif self.opcode == rfc6455.OPCODE.TEXT:
      pass
    elif self.opcode == rfc6455.OPCODE.BINARY:
      pass
    elif self.opcode == rfc6455.OPCODE.PONG or self.opcode == rfc6455.OPCODE.PING:
      if len(self.data) > 125:
        raise Exception('control frame length can not be > 125')
      pass
    else:
      # unknown or reserved opcode so just close
      raise Exception('unknown opcode')

    # 
    if self.fin == 0:
      self._handleFragmentPacket()
    else:
      self._handleCompletePacket()
      pass
    pass

  def _handleHandshake(self):
    data = self.client.recv(self.headertoread)
    if not data:
      raise Exception('remote socket closed')

    else:
      # accumulate
      self.headerbuffer.extend(data)

      if len(self.headerbuffer) >= self.maxheader:
        raise Exception('header exceeded allowable size')

      # indicates end of HTTP header
      if b'\r\n\r\n' in self.headerbuffer:
        self.request = HTTPRequest(self.headerbuffer)

        # handshake rfc 6455
        websock_key = self.request.headers.get('Sec-WebSocket-Key')
        if websock_key is None:
          hStr = rfc6455.FAILED_HANDSHAKE + "\n" + 'Sec-WebSocket-Key is not present in the request header.\n' + str(self.request.headers)
          self._sendBuffer(hStr.encode('ascii'), True)
          self.client.close()
          raise Exception('handshake failed: %s', str(exc))

        websock_key = self.request.headers['Sec-WebSocket-Key']
        key_value = websock_key.encode('ascii') + rfc6455.GUID_STR.encode('ascii')
        key_str = base64.b64encode(hashlib.sha1(key_value).digest()).decode('ascii')
        handshake_str = rfc6455.HANDSHAKE % {'acceptstr': key_str}
        try:
          self.sendq.append((rfc6455.OPCODE.BINARY, handshake_str.encode('ascii')))
          self.handshaked = True
        except Exception as exc:
          handshake_str = rfc6455.FAILED_HANDSHAKE + "\n" + str(exc)
          self._sendBuffer(handshake_str.encode('ascii'), True)
          self.client.close()
          raise Exception('handshake failed: %s', str(exc))
        
        try:
          self.handleConnected()
        except Exception as exc:
          self.client.close()
          raise Exception('handleConnected failed: %s', str(exc))
        pass
      pass
    pass

  def _handleData(self):
    # do the HTTP header and handshake
    if self.handshaked is False:
      # Handshake first
      self._handleHandshake()
      pass
    else:
      # else do normal data
      data = self.client.recv(16384)
      if not data:
        raise Exception("remote socket closed")

      for d in data:
        self._parseMessage(d)
        pass
      pass
    pass


  def close(self, status = rfc6455.STATUS.Normal_Closure, reason = u''):
    """
    Send Close frame to the client. The underlying socket is only closed
    when the client acknowledges the Close frame.

    status is the closing identifier.
    reason is the reason for the close.
    """
    try:
      if self.closed is False:
        close_msg = bytearray()
        close_msg.extend(struct.pack("!H", status))
        if is_unicode(reason):
          close_msg.extend(reason.encode('utf-8'))
          pass
        else:
          close_msg.extend(reason)
          pass

        self._sendMessage(False, rfc6455.OPCODE.CLOSE, close_msg)
        pass
      pass

    finally:
      self.closed = True
      pass
    pass


  def _sendBuffer(self, buff, send_all = False):
    size = len(buff)
    tosend = size
    already_sent = 0

    while tosend > 0:
      try:
        # i should be able to send a bytearray
        sent = self.client.send(buff[already_sent:])
        if sent == 0:
          raise RuntimeError('socket connection broken')

        already_sent += sent
        tosend -= sent
        pass

      except socket.error as socke:
        # if we have full buffers then wait for them to drain and try again
        if socke.errno in [errno.EAGAIN, errno.EWOULDBLOCK]:
          if send_all:
            continue
          return buff[already_sent:]
        else:
          raise socke
        pass
      pass

    return None

  def sendFragmentStart(self, data):
    """
    Send the start of a data fragment stream to a websocket client.
    Subsequent data should be sent using sendFragment().
    A fragment stream is completed when sendFragmentEnd() is called.

    If data is a unicode object then the frame is sent as Text.
    If the data is a bytearray object then the frame is sent as Binary.
    """
    opcode = rfc6455.OPCODE.TEXT if is_unicode(data) else rfc6455.OPCODE.BINARY
    self._sendMessage(True, opcode, data)
    pass

  def sendFragment(self, data):
    """
    see sendFragmentStart()

    If data is a unicode object then the frame is sent as Text.
    If the data is a bytearray object then the frame is sent as Binary.
    """
    self._sendMessage(True, rfc6455.OPCODE.STREAM, data)
    pass

  def sendFragmentEnd(self, data):
    """
    see sendFragmentEnd()

    If data is a unicode object then the frame is sent as Text.
    If the data is a bytearray object then the frame is sent as Binary.
    """
    self._sendMessage(False, rfc6455.OPCODE.STREAM, data)
    pass


  def sendMessage(self, data):
    """
    Send websocket data frame to the client.

    If data is a unicode object then the frame is sent as Text.
    If the data is a bytearray object then the frame is sent as Binary.
    """
    self._sendMessage(False, rfc6455.OPCODE.TEXT if is_unicode(data) else rfc6455.OPCODE.BINARY, data)
    pass
   

  def _sendMessage(self, fin, opcode, data):
    payload = bytearray()

    # First byte is opcode
    payload.append(opcode if fin else opcode | 0x80)

    if is_unicode(data):
      data = data.encode('utf-8')
      pass

    length = len(data)

    # RFC6455 - 5.2.  Base Framing Protocol
    if length <= 125:
      payload.append(length)

    elif length >= 126 and length <= 65535:
      payload.append(126)
      payload.extend(struct.pack("!H", length))

    else:
      payload.append(127)
      payload.extend(struct.pack("!Q", length))
      pass

    if length > 0:
      payload.extend(data)
      pass
    self.sendq.append((opcode, payload))
    pass


  def _parseMessage(self, byte):
    self.state(byte)
    pass

  # 
  def _STATE_HEADER_FIRSTBYTE(self, byte):
    self.state = self._STATE_HEADER_SECONDBYTE
    self.fin = byte & 0x80
    self.opcode = byte & 0x0F
    self.index = 0
    self.length = 0
    self.lengtharray = bytearray()
    self.data = bytearray()

    rsv = byte & 0x70
    if rsv != 0:
      raise Exception('RSV bit must be 0')
    pass

  def _STATE_HEADER_SECONDBYTE(self, byte):
    mask = byte & 0x80
    length = byte & 0x7F

    if self.opcode == rfc6455.OPCODE.PING and length > 125:
      raise Exception('ping packet is too large')

    if mask == 128:
      self.hasmask = True
    else:
      self.hasmask = False
      pass

    if length <= 125:
      self.length = length

      # if we have a mask we must read it
      if self.hasmask is True:
        self.maskarray = bytearray()
        self.state = self._STATE_MASK
      else:
        # if there is no mask and no payload we are done
        if self.length <= 0:
          try:
            self._handlePacket()
          finally:
            self.state = self._STATE_HEADER_FIRSTBYTE
            self.data = bytearray()
            pass
          pass

        # we have no mask and some payload
        else:
          self.data = bytearray()
          self.state = self._STATE_PAYLOAD
          pass
        pass
      pass
    elif length == 126:
      self.lengtharray = bytearray()
      self.state = self._STATE_LENGTH_SHORT

    elif length == 127:
      self.lengtharray = bytearray()
      self.state = self._STATE_LENGTH_LONG
      pass
    pass
  
  def _STATE_LENGTH_SHORT(self, byte):
    self.lengtharray.append(byte)

    if len(self.lengtharray) > 2:
      raise Exception('short length exceeded allowable size')

    if len(self.lengtharray) == 2:
      self.length = struct.unpack_from('!H', self.lengtharray)[0]

      if self.hasmask is True:
        self.maskarray = bytearray()
        self.state = self._STATE_MASK
      else:
        # if there is no mask and no payload we are done
        if self.length <= 0:
          try:
            self._handlePacket()
          finally:
            self.state = self._STATE_HEADER_FIRSTBYTE
            self.data = bytearray()
            pass
          pass

        # we have no mask and some payload
        else:
          self.data = bytearray()
          self.state = self._STATE_PAYLOAD
          pass
        pass
      pass
    pass

  def _STATE_LENGTH_LONG(self, byte):
    self.lengtharray.append(byte)

    if len(self.lengtharray) > 8:
      raise Exception('long length exceeded allowable size')

    if len(self.lengtharray) == 8:
      self.length = struct.unpack_from('!Q', self.lengtharray)[0]
      pass

    if self.hasmask is True:
      self.maskarray = bytearray()
      self.state = self._STATE_MASK
    else:
      # if there is no mask and no payload we are done
      if self.length <= 0:
        try:
          self._handlePacket()
        finally:
          self.state = self._STATE_HEADER_FIRSTBYTE
          self.data = bytearray()
          pass

        # we have no mask and some payload
      else:
        self.data = bytearray()
        self.state = self._STATE_PAYLOAD
        pass
      pass
    pass

  # MASK STATE
  def _STATE_MASK(self, byte):
    self.maskarray.append(byte)

    if len(self.maskarray) > 4:
      raise Exception('mask exceeded allowable size')

    if len(self.maskarray) == 4:
      # if there is no mask and no payload we are done
      if self.length <= 0:
        try:
          self._handlePacket()
        finally:
          self.state = self._STATE_HEADER_FIRSTBYTE
          self.data = bytearray()
          pass
        pass

      # we have no mask and some payload
      else:
        self.data = bytearray()
        self.state = self._STATE_PAYLOAD
        pass
      pass
    pass

  # PAYLOAD STATE
  def _STATE_PAYLOAD(self, byte):
    if self.hasmask is True:
      self.data.append( byte ^ self.maskarray[self.index % 4] )
    else:
      self.data.append( byte )
      pass

    # if length exceeds allowable size then we except and remove the connection
    if len(self.data) >= self.maxpayload:
      raise Exception('payload exceeded allowable size')

    # check if we have processed length bytes; if so we are done
    if (self.index+1) == self.length:
      try:
        self._handlePacket()
      finally:
        self.state = self._STATE_HEADER_FIRSTBYTE
        self.data = bytearray()
        pass
    else:
      self.index += 1
      pass
    pass

  pass # End of class


class VanillaWebSocketServer(object):
  def __init__(self, host, port, websocketclass, selectInterval = 0.1):
    self.websocketclass = websocketclass

    host = None if host == '' else host
    fam = socket.AF_INET6 if host is None else 0

    hostInfo = socket.getaddrinfo(host, port, fam, socket.SOCK_STREAM, socket.IPPROTO_TCP, socket.AI_PASSIVE)
    self.serversocket = socket.socket(hostInfo[0][0], hostInfo[0][1], hostInfo[0][2])
    self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.serversocket.bind(hostInfo[0][4])
    self.serversocket.listen(5)
    self.selectInterval = selectInterval
    self.connections = {}
    self.listeners = [self.serversocket]
    pass

  def _decorateSocket(self, sock):
    return sock

  def _constructWebSocket(self, sock, address):
    return self.websocketclass(self, sock, address)

  def close(self):
    self.serversocket.close()

    for desc, conn in self.connections.items():
      conn.close()
      self._handleClose(conn)
      pass
    pass

  def _handleClose(self, client):
    client.client.close()
    # only call handleClose when we have a successful websocket connection
    if client.handshaked:
      try:
        client.handleClose()
      except Exception as exc:
        print("close handle: " + str(exc))
        pass
      pass
    pass

  def dispatch(self):
    writers = []
    for fileno in self.listeners:
      if fileno == self.serversocket:
        continue
      client = self.connections[fileno]
      if client.sendq:
        writers.append(fileno)
        pass
      pass

    rList, wList, xList = select(self.listeners, writers, self.listeners, self.selectInterval)

    for ready in wList:
      client = self.connections[ready]
      try:
        while client.sendq:
          opcode, payload = client.sendq.popleft()
          remaining = client._sendBuffer(payload)
          if remaining is not None:
            client.sendq.appendleft((opcode, remaining))
            break
          else:
            if opcode == rfc6455.OPCODE.CLOSE:
              raise Exception('received client close')
            pass
          pass

      except Exception as exc:
        print("write select: " + str(exc))
        self._handleClose(client)
        del self.connections[ready]
        self.listeners.remove(ready)
        pass
      pass

    for ready in rList:
      if ready == self.serversocket:
        sock = None
        try:
          sock, address = self.serversocket.accept()
          newsock = self._decorateSocket(sock)
          newsock.setblocking(0)
          fileno = newsock.fileno()
          self.connections[fileno] = self._constructWebSocket(newsock, address)
          self.listeners.append(fileno)
        except Exception as exc:
          print( "constructing web socket failed - " + str(exc))
          if sock is not None:
            sock.close()
            pass
          pass
        pass
      else:
        if ready not in self.connections:
          continue
        client = self.connections[ready]
        try:
          client._handleData()
        except Exception as exc:
          print("handle data failed" + str(exc))
          self._handleClose(client)
          del self.connections[ready]
          self.listeners.remove(ready)
          pass
        pass
      pass
        
    for failed in xList:
      if failed == self.serversocket:
        self.close()
        raise Exception('server socket failed')
      else:
        if failed not in self.connections:
          continue
        client = self.connections[failed]
        self._handleClose(client)
        del self.connections[failed]
        self.listeners.remove(failed)
        pass
      pass
    pass

  def run(self):
    while True:
      self.dispatch()
      pass
    pass
  pass

import ssl
class VanillaSSLWebSocketServer(VanillaWebSocketServer):

  def __init__(self, host, port, websocketclass, certfile = None,
               keyfile = None, version = ssl.PROTOCOL_TLSv1, selectInterval = 0.1, ssl_context = None):

    VanillaWebSocketServer.__init__(self, host, port,
                                    websocketclass, selectInterval)

    if ssl_context is None:
      self.context = ssl.SSLContext(version)
      self.context.load_cert_chain(certfile, keyfile)
    else:
      self.context = ssl_context
      pass
    pass

  def close(self):
    super(VanillaSSLWebSocketServer, self).close()
    pass

  def _decorateSocket(self, sock):
    sslsock = self.context.wrap_socket(sock, server_side=True)
    return sslsock

  def _constructWebSocket(self, sock, address):
    ws = self.websocketclass(self, sock, address)
    ws.usingssl = True
    return ws

  def serveforever(self):
    super(VanillaSSLWebSocketServer, self).serveforever()
    pass
  pass


if __name__ == "__main__":
  parser = OptionParser(usage="usage: %prog [options]", version="%prog 1.0")
  parser.add_option("--host", default='', type='string', action="store", dest="host", help="hostname (localhost)")
  parser.add_option("--port", default=7777, type='int', action="store", dest="port", help="port (7777)")
  (options, args) = parser.parse_args()
  server = VanillaWebSocketServer(options.host, options.port, ChatClient)

  #def close_sig_handler(signal, frame):
  #  server.close()
  #  sys.exit()
  #  pass

  #signal.signal(signal.SIGINT, close_sig_handler)
  server.run()
  pass
