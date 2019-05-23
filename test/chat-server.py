#!/usr/bin/python3

import sys, os
sys.path.append(os.path.join(os.getcwd(), '../lib'))

from VanillaWebSocketServer import  *

from optparse import OptionParser

class ChatClient(WebSocketConnection):
  clients = []

  def __init__(self, server, sock, address):
    WebSocketConnection.__init__(self, server, sock, address)
    pass
    
  def handleMessage(self):
    for client in self.clients:
      if client != self:
        client.sendMessage(self.address[0] + u' - ' + self.data)
        pass
      pass
    pass

  def handleConnected(self):
    for client in self.clients:
      client.sendMessage(self.address[0] + u' - connected')
      pass
    self.clients.append(self)
    pass

  def handleClose(self):
    self.clients.remove(self)
    print (self.address, 'closed')
    for client in self.clients:
      client.sendMessage(self.address[0] + u' - disconnected')
      pass
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
