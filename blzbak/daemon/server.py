"""Main TCP server for blzbakd daemon.

Multi-threaded server that:
- Listens on a TCP port for client connections
- Spawns a worker thread for each client
- Uses the protocol handler to process requests
"""

import logging
import socket
import struct
import sys
import threading
from typing import Optional

# Import protocol definitions from the main blzbak package
sys.path.insert(0, '/home/blizz/proj/blzbak/blzbak')
from blzbak.protocol import (
    HEADER_SIZE, encode_message, decode_message, unpack_header, pack_header
)

from .config import DaemonConfig
from .storage import StorageManager
from .handler import ProtocolHandler


logger = logging.getLogger(__name__)


class ClientHandler(threading.Thread):
    """Thread that handles a single client connection."""

    def __init__(
        self,
        client_socket: socket.socket,
        client_address: tuple,
        handler: ProtocolHandler,
    ):
        super().__init__(daemon=True)
        self.client_socket = client_socket
        self.client_address = client_address
        self.handler = handler
        self.running = True

    def run(self):
        """Handle client requests in a loop."""
        logger.info(f"Client connected: {self.client_address}")
        
        try:
            while self.running:
                # Read message header (4 bytes)
                try:
                    header_data = self._recv_exactly(HEADER_SIZE)
                    if not header_data:
                        break
                except ConnectionError:
                    break
                
                # Parse message length
                msg_len = unpack_header(header_data)
                
                # Read message body
                try:
                    body_data = self._recv_exactly(msg_len)
                    if not body_data:
                        break
                except ConnectionError:
                    break
                
                # Decode and process request
                try:
                    request = decode_message(body_data)
                    response = self.handler.handle_request(request)
                except Exception as e:
                    logger.error(f"Error processing request: {e}", exc_info=True)
                    response = {"status": "error", "message": f"Internal error: {e}"}
                
                # Send response
                try:
                    response_data = encode_message(response)
                    self.client_socket.sendall(response_data)
                except Exception as e:
                    logger.error(f"Error sending response: {e}")
                    break
                    
        except Exception as e:
            logger.error(
                f"Unexpected error handling client {self.client_address}: {e}",
                exc_info=True
            )
        finally:
            self.close()

    def _recv_exactly(self, n: int) -> bytes:
        """Receive exactly n bytes from the socket."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self.client_socket.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by client")
            buf.extend(chunk)
        return bytes(buf)

    def close(self):
        """Close the client connection."""
        self.running = False
        try:
            self.client_socket.close()
        except:
            pass
        logger.info(f"Client disconnected: {self.client_address}")


class DaemonServer:
    """Multi-threaded TCP server for blzbakd."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self.storage = StorageManager(config.base_path, config.diff_dir, config)
        self.handler = ProtocolHandler(self.storage)
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self.client_threads = []

    def start(self):
        """Start the daemon server."""
        # Create server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.config.host, self.config.port))
            self.server_socket.listen(5)
            self.running = True
            
            logger.info(
                f"blzbakd listening on {self.config.host}:{self.config.port}"
            )
            logger.info(f"Backup storage: {self.config.base_path}")
            logger.info(f"Diff storage: {self.config.diff_dir}")
            
            self._accept_loop()
            
        except OSError as e:
            logger.error(f"Failed to bind to {self.config.host}:{self.config.port}: {e}")
            raise
        finally:
            self.stop()

    def _accept_loop(self):
        """Accept client connections in a loop."""
        while self.running:
            try:
                # Accept with timeout so we can check self.running periodically
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self.server_socket.accept()
                except socket.timeout:
                    continue
                
                # Spawn a handler thread for this client
                client_thread = ClientHandler(
                    client_socket, client_address, self.handler
                )
                client_thread.start()
                self.client_threads.append(client_thread)
                
                # Clean up finished threads
                self.client_threads = [
                    t for t in self.client_threads if t.is_alive()
                ]
                
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}", exc_info=True)

    def stop(self):
        """Stop the daemon server."""
        logger.info("Shutting down blzbakd...")
        self.running = False
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Wait for client threads to finish (with timeout)
        for thread in self.client_threads:
            thread.join(timeout=2.0)
        
        logger.info("blzbakd stopped")
