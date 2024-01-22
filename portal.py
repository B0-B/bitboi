#####################################################################################
#####################################################################################
# Captive Portal Code © 2024
# Copyright © 2024 github.com/B0-B
#####################################################################################
#####################################################################################

import gc
import os
import time
import network
import machine
import usocket
import uasyncio
import json


# ========== Baked Phew Dependencies ==========

# Exctracted from official repository: https://github.com/pimoroni/phew
# highly recommended to set a lowish garbage collection threshold
# to minimise memory fragmentation as we sometimes want to
# allocate relatively large blocks of ram.
gc.threshold(50000)

# determine if remotely mounted or not, changes some behaviours like
# logging truncation
remote_mount = False
try:
  os.statvfs(".") # causes exception if remotely mounted (mpremote/pyboard.py)
except:
  remote_mount = True

# helper method to put the pico into access point mode
def access_point(ssid, password = None):
  # start up network in access point mode  
  wlan = network.WLAN(network.AP_IF)
  wlan.config(essid=ssid)
  if password:
    wlan.config(password=password)
  else:    
    wlan.config(security=0) # disable password
  wlan.active(True)
  return wlan

# template.py
async def render_template(template, **kwargs):
  start_time = time.ticks_ms()
  with open(template, "rb") as f:
    # read the whole template file, we could work on single lines but
    # the performance is much worse - so long as our templates are
    # just a handful of kB it's ok to do this
    data = f.read()
    token_caret = 0
    while True:
      # find the next tag that needs evaluating
      start = data.find(b"{{", token_caret)
      end = data.find(b"}}", start)
      match = start != -1 and end != -1
      # no more magic to handle, just return what's left
      if not match:
        yield data[token_caret:]
        break
      expression = data[start + 2:end].strip()
      # output the bit before the tag
      yield data[token_caret:start]
      # merge locals with the supplied named arguments and
      # the response object
      params = {}
      params.update(locals())
      params.update(kwargs)
      #params["response"] = response
      # parse the expression
      try:
        if expression.decode("utf-8") in params:
          result = params[expression.decode("utf-8")]
          result = result.replace("&", "&amp;")
          result = result.replace('"', "&quot;")
          result = result.replace("'", "&apos;")
          result = result.replace(">", "&gt;")
          result = result.replace("<", "&lt;")
        else:
          result = eval(expression, globals(), params)
        if type(result).__name__ == "generator":
          # if expression returned a generator then iterate it fully
          # and yield each result
          for chunk in result:
            yield chunk
        else:
          # yield the result of the expression
          if result:
            yield str(result)
      except:
        pass
      # discard the parsed bit
      token_caret = end + 2


# server.py
_routes = []
catchall_handler = None

def file_exists(filename):
  try:
    return (os.stat(filename)[0] & 0x4000) == 0
  except OSError:
    return False

def urldecode(text):
  text = text.replace("+", " ")
  result = ""
  token_caret = 0
  # decode any % encoded characters
  while True:
    start = text.find("%", token_caret)
    if start == -1:
      result += text[token_caret:]
      break
    result += text[token_caret:start]
    code = int(text[start + 1:start + 3], 16)
    result += chr(code)
    token_caret = start + 3
  return result

def _parse_query_string(query_string):
  result = {}
  for parameter in query_string.split("&"):
    key, value = parameter.split("=", 1)
    key = urldecode(key)
    value = urldecode(value)
    result[key] = value
  return result

class Request:
  def __init__(self, method, uri, protocol):
    self.method = method
    self.uri = uri
    self.protocol = protocol
    self.form = {}
    self.data = {}
    self.query = {}
    query_string_start = uri.find("?") if uri.find("?") != -1 else len(uri)
    self.path = uri[:query_string_start]
    self.query_string = uri[query_string_start + 1:]
    if self.query_string:
      self.query = _parse_query_string(self.query_string)

  def __str__(self):
    return f"""request: {self.method} {self.path} {self.protocol}
headers: {str(self.headers)}
form: {str(self.form)}
data: {str(self.data)}"""

class Response:
  def __init__(self, body, status=200, headers={}):
    self.status = status
    self.headers = headers
    self.body = body

  def add_header(self, name, value):
    self.headers[name] = value

  def __str__(self):
    return f"""status: {self.status}
headers: {str(self.headers)}
body: {str(self.body)}"""

content_type_map = {
  "html": "text/html",
  "jpg": "image/jpeg",
  "jpeg": "image/jpeg",
  "svg": "image/svg+xml",
  "json": "application/json",
  "png": "image/png",
  "css": "text/css",
  "js": "text/javascript",
  "csv": "text/csv",
}

class FileResponse(Response):
  def __init__(self, file, status=200, headers={}):
    self.status = 404
    self.headers = headers
    self.file = file

    try:
      if (os.stat(self.file)[0] & 0x4000) == 0:
        self.status = 200

        # auto set content type
        extension = self.file.split(".")[-1].lower()
        if extension in content_type_map:
          headers["Content-Type"] = content_type_map[extension]

        headers["Content-Length"] = os.stat(self.file)[6]
    except OSError:
      return False


class Route:
  def __init__(self, path, handler, methods=["GET"]):
    self.path = path
    self.methods = methods
    self.handler = handler
    self.path_parts = path.split("/")

  # returns True if the supplied request matches this route
  def matches(self, request):
    if request.method not in self.methods:
      return False
    compare_parts = request.path.split("/")
    if len(compare_parts) != len(self.path_parts):
      return False
    for i, compare in enumerate(compare_parts):
      part = self.path_parts[i]
      is_parameter = len(part) > 0 and part[0] == "<"
      if not is_parameter and part != compare:
        return False
    return True

  # call the route handler passing any named parameters in the path
  def call_handler(self, request):
    parameters = {}
    compare_parts = request.path.split("/")
    for i, compare in enumerate(compare_parts):
      part = self.path_parts[i]
      is_parameter = len(part) > 0 and part[0] == "<"
      if is_parameter:
        name = part[1:-1]
        parameters[name] = compare

    return self.handler(request, **parameters)
        
  def __str__(self):
    return f"""path: {self.path}
methods: {str(self.methods)}
"""

  def __repr__(self):
    return f"<Route object {self.path} ({', '.join(self.methods)})>"

# parses the headers for a http request (or the headers attached to
# each field in a multipart/form-data)
async def _parse_headers(reader):
  headers = {}
  while True:
    header_line = await reader.readline()
    if header_line == b"\r\n": # crlf denotes body start
      break
    name, value = header_line.decode().strip().split(": ", 1)
    headers[name.lower()] = value
  return headers

# returns the route matching the supplied path or None
def _match_route(request):
  for route in _routes:
    if route.matches(request):
      return route
  return None

async def _parse_form_data(reader, headers):
    return

# if the content type is application/json then parse the body
async def _parse_json_body(reader, headers):
  import json
  content_length_bytes = int(headers["content-length"])
  body = await reader.readexactly(content_length_bytes)
  return json.loads(body.decode())


status_message_map = {
  200: "OK", 201: "Created", 202: "Accepted", 
  203: "Non-Authoritative Information", 204: "No Content",
  205: "Reset Content", 206: "Partial Content", 300: "Multiple Choices",
  301: "Moved Permanently", 302: "Found", 303: "See Other",
  304: "Not Modified", 305: "Use Proxy", 306: "Switch Proxy",
  307: "Temporary Redirect", 308: "Permanent Redirect",
  400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
  404: "Not Found", 405: "Method Not Allowed", 406: "Not Acceptable",
  408: "Request Timeout", 409: "Conflict", 410: "Gone",
  414: "URI Too Long", 415: "Unsupported Media Type", 
  416: "Range Not Satisfiable", 418: "I'm a teapot",
  500: "Internal Server Error", 501: "Not Implemented"
}


# handle an incoming request to the web server
async def _handle_request(reader, writer):
  response = None
  request_start_time = time.ticks_ms()
  request_line = await reader.readline()
  try:
    method, uri, protocol = request_line.decode().split()
  except Exception as e:
    return
  request = Request(method, uri, protocol)
  request.headers = await _parse_headers(reader)
  if "content-length" in request.headers and "content-type" in request.headers:
    if request.headers["content-type"].startswith("multipart/form-data"):
      request.form = await _parse_form_data(reader, request.headers)
    if request.headers["content-type"].startswith("application/json"):
      request.data = await _parse_json_body(reader, request.headers)
    if request.headers["content-type"].startswith("application/x-www-form-urlencoded"):
      form_data = await reader.read(int(request.headers["content-length"]))
      request.form = _parse_query_string(form_data.decode()) 
  route = _match_route(request)
  if route:
    response = route.call_handler(request)
  elif catchall_handler:
    response = catchall_handler(request)
  # if shorthand body generator only notation used then convert to tuple
  if type(response).__name__ == "generator":
    response = (response,)
  # if shorthand body text only notation used then convert to tuple
  if isinstance(response, str):
    response = (response,)
  # if shorthand tuple notation used then build full response object
  if isinstance(response, tuple):
    body = response[0]
    status = response[1] if len(response) >= 2 else 200
    content_type = response[2] if len(response) >= 3 else "text/html"
    response = Response(body, status=status)
    response.add_header("Content-Type", content_type)
    if hasattr(body, '__len__'):
      response.add_header("Content-Length", len(body))
  # write status line
  status_message = status_message_map.get(response.status, "Unknown")
  writer.write(f"HTTP/1.1 {response.status} {status_message}\r\n".encode("ascii"))
  # write headers
  for key, value in response.headers.items():
    writer.write(f"{key}: {value}\r\n".encode("ascii"))
  # blank line to denote end of headers
  writer.write("\r\n".encode("ascii"))
  if isinstance(response, FileResponse):
    # file
    with open(response.file, "rb") as f:
      while True:
        chunk = f.read(1024)
        if not chunk:
          break
        writer.write(chunk)
        await writer.drain()
  elif type(response.body).__name__ == "generator":
    # generator
    for chunk in response.body:
      writer.write(chunk)
      await writer.drain()
  else:
    # string/bytes
    writer.write(response.body)
    await writer.drain()
  writer.close()
  await writer.wait_closed()
  processing_time = time.ticks_ms() - request_start_time
  print(f"> {request.method} {request.path} ({response.status} {status_message}) [{processing_time}ms]")

# adds a new route to the routing table
def add_route(path, handler, methods=["GET"]):
  global _routes
  _routes.append(Route(path, handler, methods))
  # descending complexity order so most complex routes matched first
  _routes = sorted(_routes, key=lambda route: len(route.path_parts), reverse=True)


def set_callback(handler):
  global catchall_handler
  catchall_handler = handler


# decorator shorthand for adding a route
def route(path, methods=["GET"]):
  def _route(f):
    add_route(path, f, methods=methods)
    return f
  return _route


# decorator for adding catchall route
def catchall():
  def _catchall(f):
    set_callback(f)
    return f
  return _catchall

def run(host = "0.0.0.0", port = 80):

  loop = uasyncio.get_event_loop()
  loop.create_task(uasyncio.start_server(_handle_request, host, port))
  loop.run_forever()


# -- dns.py --
async def _handler(socket, ip_address):
  while True:
    try:
      yield uasyncio.core._io_queue.queue_read(socket)
      request, client = socket.recvfrom(256)
      response = request[:2] # request id
      response += b"\x81\x80" # response flags
      response += request[4:6] + request[4:6] # qd/an count
      response += b"\x00\x00\x00\x00" # ns/ar count
      response += request[12:] # origional request body
      response += b"\xC0\x0C" # pointer to domain name at byte 12
      response += b"\x00\x01\x00\x01" # type and class (A record / IN class)
      response += b"\x00\x00\x00\x3C" # time to live 60 seconds
      response += b"\x00\x04" # response length (4 bytes = 1 ipv4 address)
      response += bytes(map(int, ip_address.split("."))) # ip address parts
      socket.sendto(response, client)
    except Exception as e:
      print(e)

def run_catchall(ip_address, port=53):
  print("> starting catch all dns server on port {}".format(port))

  _socket = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
  _socket.setblocking(False)
  _socket.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
  _socket.bind(usocket.getaddrinfo(ip_address, port, 0, usocket.SOCK_DGRAM)[0][-1])

  loop = uasyncio.get_event_loop()
  loop.create_task(_handler(_socket, ip_address))
# ========== Dependencies End ==========


# ========== Code ==========
def spawn ():
    
    '''
    Spawns a captive portal at specified address.
    '''
    
    # -- global parameters --
    APNAME = "bitboi captive" # the 
    DOMAIN = "bitboi.access"  # This is the address that is shown on the Captive Portal
    TIMEOUT = 10

    # ========== build access point with callback ===========
    @route("/", methods=['GET'])
    def index(request):
        """ Render the Index page"""
        if request.method == 'GET':
            return render_template("index.html")

    # apple redir
    @route("/hotspot-detect.html", methods=["GET"])
    def hotspot(request):
        print(request)
        """ Redirect to the Index Page """
        return render_template("index.html")

    # ========== define API end-point ===========
    @route("/login", ["POST"])
    def login_form(request):
        status, message = 404, 'none'
        try:
            # load current config state
            config = None
            with open('config.json') as f:
                config = json.load(f)
            # override config
            config['ssid'] = request.data['ssid']
            config['wpa2'] = request.data['wpa2']
            # dump
            with open('config.json', 'w+') as f:
                f.write(json.dumps(config))
            status, message = 200, 'ok'
        except Exception as e:
            status, message = 500, 'fail'
        finally:
            # wrap up the json package and send
            return Response(json.dumps({'message': message}), status=status, headers={"Content-Type": "application/json"})

    # ========== Initialize Service ===========
    # Set to Accesspoint mode
    # Change this to whatever Wifi SSID you wish
    ap = access_point(APNAME)
    ip = ap.ifconfig()[0]
    # Grab the IP address and store it
    print(f"starting DNS server on {ip}")
    # # Catch all requests and reroute them
    run_catchall(ip)
    run()                            # Run the server
