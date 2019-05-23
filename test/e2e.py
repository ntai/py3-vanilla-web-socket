#!/usr/bin/python3

import subprocess, os, sys, socket, time

HTTP_PORT='8002'
WEBSOCKET_PORT='8003'

sys.path.append(os.path.join(os.getcwd(), "../lib"))

templatefile = open('index.html.template')
index_html = templatefile.read()
templatefile.close()

index_html_file = open('index.html', 'w')
for line in index_html.splitlines():
  if 'HOSTNAME' in line:
    index_html_file.write(line.format(HOSTNAME=socket.getfqdn(), PORT=WEBSOCKET_PORT))
  else:
    index_html_file.write(line)
    pass
  index_html_file.write('\n')
  pass
index_html_file.close()

httpserver = subprocess.Popen(['python3', 'httpserver.py', HTTP_PORT], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
websockserver = subprocess.Popen(['python3', 'chat-server.py', '--port', WEBSOCKET_PORT], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(5)
browser = subprocess.Popen(['x-www-browser', 'http://localhost:{PORT}'.format(PORT=HTTP_PORT)])

time.sleep(5)
httpserver.kill()
websockserver.kill()
