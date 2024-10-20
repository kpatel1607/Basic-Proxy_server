import asyncio

# Configuring the proxy server
PROXY_HOST = '0.0.0.0'  # To listen on all available interfaces
PROXY_PORT = 8080        # The port your proxy server will run on

BUFFER_SIZE = 4096  # Size of buffer to receive data
MAX_WORKERS = 100
BLOCKED_HOSTS = ['www.example.com']

async def handle_client(reader, writer):
    try:
        print("Handling client connection...")
        request = await reader.read(BUFFER_SIZE)
        print(f"Received request:\n{request.decode('utf-8')}")

        # Extracting the destination host and port from the client's request
        target_host, target_port = get_target_host(request)

        # Check if the target host is blocked
        if target_host in BLOCKED_HOSTS:
            print(f"Blocked access to {target_host}")
            await send_forbidden(writer)
            return

        if target_host is None:
            print("Blocked or invalid request")
            writer.close()
            return

        # Forward the HTTP/HTTPS request
        if request.startswith(b'CONNECT'):  # HTTPS request
            await handle_https(reader, writer, target_host, target_port)
        else:  # HTTP request
            await forward_http(reader, writer, request, target_host, target_port)

    except Exception as e:
        print(f"Error handling client: {e}")
        writer.close()

async def handle_https(reader, writer, target_host, target_port):
    """Handles the HTTPS connection by setting up a tunnel."""
    if target_host in BLOCKED_HOSTS:
        print(f"Blocked access to {target_host}")
        await send_forbidden(writer)
        return

    try:
        # Send a 200 Connection Established response to the client
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        # Create a connection to the target server
        server_reader, server_writer = await asyncio.open_connection(target_host, target_port)

        # Relay data between client and server
        await asyncio.gather(relay(reader, server_writer), relay(server_reader, writer))

    except Exception as e:
        print(f"Error handling HTTPS: {e}")
        writer.close()

async def forward_http(reader, writer, request, target_host, target_port):
    """Handles forwarding HTTP requests to the target server."""
    try:
        # Create a connection to the target server
        server_reader, server_writer = await asyncio.open_connection(target_host, target_port)

        # Send the client's request to the target server
        server_writer.write(request)
        await server_writer.drain()

        # Relay the response from the server back to the client
        await asyncio.gather(relay(server_reader, writer))

    except Exception as e:
        print(f"Error handling HTTP: {e}")
    finally:
        writer.close()

async def relay(reader, writer):
    """Relays data between reader and writer streams."""
    try:
        while True:
            data = await reader.read(BUFFER_SIZE)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception as e:
        print(f"Error relaying data: {e}")
    finally:
        writer.close()

def get_target_host(request):
    try:
        # Decode the request to check its contents
        request_str = request.decode('utf-8')

        # For HTTPS requests (CONNECT method), the host is the first line after CONNECT
        if request_str.startswith('CONNECT'):
            target_host_line = request_str.split('\n')[0]
            target_host_port = target_host_line.split(' ')[1]
            target_host, target_port = target_host_port.split(':')
            return target_host, int(target_port)
        
        # For normal HTTP requests
        lines = request_str.split('\n')
        for line in lines:
            if line.startswith('Host:'):
                target_host = line.split(' ')[1].strip()
                return target_host, 80  # Default HTTP port is 80
        return None, None
    except Exception as e:
        print(f"Error extracting target host: {e}")
        return None, None

async def send_forbidden(writer):
    """Send a 403 Forbidden response to the client"""
    response = (
        "HTTP/1.1 403 Forbidden\r\n"
        "Content-Type: text/html\r\n"
        "Content-Length: 58\r\n"
        "\r\n"
        "<html><body><h1>403 Forbidden: Access Denied</h1></body></html>"
    )
    writer.write(response.encode('utf-8'))
    await writer.drain()
    writer.close()

async def start_proxy():
    # Create a socket to listen for incoming connections
    server = await asyncio.start_server(handle_client, PROXY_HOST, PROXY_PORT)
    print(f"[*] Proxy server listening on {PROXY_HOST}:{PROXY_PORT}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(start_proxy())
