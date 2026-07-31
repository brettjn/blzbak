"""Protocol handler for blzbakd — processes client commands.

Handles all protocol commands defined in blzbak.protocol:
- PING
- PREPARE_BACKUP
- BACKUP_COMPLETE
- LIST_SETS
- LIST_SNAPSHOTS
- LIST_FILES
"""

import logging
import sys
from typing import Dict, Any

# Import protocol definitions from the main blzbak package
sys.path.insert(0, '/home/blizz/proj/blzbak/blzbak')
from blzbak.protocol import Command

from .storage import StorageManager
import json


logger = logging.getLogger(__name__)


class ProtocolHandler:
    """Handles blzbak protocol commands."""

    def __init__(self, storage: StorageManager):
        self.storage = storage
        
        # Command dispatch table
        self._handlers = {
            Command.PING: self._handle_ping,
            Command.TEST: self._handle_test,
            Command.CREATE_SET: self._handle_create_set,
            Command.PREPARE_BACKUP: self._handle_prepare_backup,
            Command.BACKUP_COMPLETE: self._handle_backup_complete,
            Command.LIST_SETS: self._handle_list_sets,
            Command.LIST_SNAPSHOTS: self._handle_list_snapshots,
            Command.LIST_FILES: self._handle_list_files,
            Command.DELETE_SET: self._handle_delete_set,
            Command.SHOW_SET: self._handle_show_set,
            Command.FILES_DIFF: self._handle_files_diff,
        }

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a client request and return a response.
        
        Args:
            request: Decoded JSON request dict with 'cmd' field
            
        Returns:
            Response dict with 'status' field ('ok' or 'error')
        """
        cmd = request.get("cmd")
        
        if not cmd:
            return self._error_response("Missing 'cmd' field in request")
        
        handler = self._handlers.get(cmd)
        if not handler:
            return self._error_response(f"Unknown command: {cmd}")
        
        try:
            logger.debug(f"Handling command: {cmd}")
            response = handler(request)
            logger.debug(f"Command {cmd} completed successfully")
            return response
        except Exception as e:
            logger.error(f"Error handling {cmd}: {e}", exc_info=True)
            return self._error_response(str(e))

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _handle_ping(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle PING command - simple health check."""
        return {"status": "ok", "message": "pong"}

    def _handle_test(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle TEST command - return daemon configuration and status."""
        from .config import DaemonConfig
        import os
        
        # Get current daemon configuration
        config = self.storage.config if hasattr(self.storage, 'config') else None
        
        # Build response with daemon info
        response = {
            "status": "ok",
            "message": "Test successful",
            "daemon": {
                "base_path": str(self.storage.base_path),
            },
            "sets": [],
        }
        
        # Add configuration details if available
        if config:
            response["daemon"]["port"] = config.port
            response["daemon"]["host"] = config.host
            response["daemon"]["max_workers"] = config.max_workers
            response["daemon"]["log_level"] = config.log_level
            response["daemon"]["config_source"] = config.config_source
        
        # Check if base_path exists and is writable
        base_path = self.storage.base_path
        response["daemon"]["base_path_exists"] = os.path.exists(base_path)
        response["daemon"]["base_path_writable"] = os.access(base_path, os.W_OK) if os.path.exists(base_path) else False
        
        # List all backup sets with basic info
        try:
            sets = self.storage.list_sets()
            for set_name in sets:
                set_info = {"name": set_name}
                try:
                    # Get snapshot info
                    c_snap = self.storage.get_snapshot_info(set_name, "C")
                    o_snap = self.storage.get_snapshot_info(set_name, "O")
                    set_info["snapshots"] = {
                        "C": c_snap.to_dict() if c_snap.exists else None,
                        "O": o_snap.to_dict() if o_snap.exists else None,
                    }
                except Exception as e:
                    set_info["error"] = str(e)
                response["sets"].append(set_info)
        except Exception as e:
            logger.error(f"Failed to list sets during test: {e}")
            response["sets_error"] = str(e)
        
        return response

    def _handle_create_set(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle CREATE_SET command - create a new backup set with metadata."""
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        metadata = request.get("metadata", {})
        
        logger.info(f"Creating backup set '{set_name}'")
        
        try:
            result = self.storage.create_set(set_name, metadata)
            
            return {
                "status": "ok",
                "message": f"Backup set '{set_name}' created successfully",
                "details": result,
            }
        except Exception as e:
            logger.error(f"Failed to create backup set '{set_name}': {e}")
            return self._error_response(f"Failed to create backup set: {e}")

    def _handle_prepare_backup(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle PREPARE_BACKUP command.
        
        Creates diffs between C and O, then syncs O to match C.
        This prepares the server to receive a new backup via rsync.
        """
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        logger.info(f"Preparing backup for set '{set_name}'")
        
        try:
            result = self.storage.prepare_backup(set_name)
            
            return {
                "status": "ok",
                "message": f"Backup preparation complete for '{set_name}'",
                "details": result,
            }
        except Exception as e:
            logger.error(f"Failed to prepare backup for '{set_name}': {e}")
            return self._error_response(f"Backup preparation failed: {e}")

    def _handle_backup_complete(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle BACKUP_COMPLETE command.
        
        Notifies the daemon that the client has finished rsync.
        This is mainly for logging and potential future hooks.
        """
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        logger.info(f"Backup completed for set '{set_name}'")
        # Update metadata and log finish time
        try:
            finished_meta = self.storage.mark_backup_complete(set_name)
        except Exception as e:
            logger.warning(f"Failed to update backup completion metadata for '{set_name}': {e}")
            # Continue to return OK but warn the client

        # Get snapshot info for confirmation
        c_info = self.storage.get_snapshot_info(set_name, "C")
        
        return {
            "status": "ok",
            "message": f"Backup complete for '{set_name}'",
            "snapshot": c_info.to_dict() if c_info.exists else None,
            "metadata": finished_meta if 'finished_meta' in locals() else None,
        }

    def _handle_list_sets(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LIST_SETS command - return all backup sets."""
        try:
            sets = self.storage.list_sets()
            return {
                "status": "ok",
                "sets": [{"name": s} for s in sets],
            }
        except Exception as e:
            logger.error(f"Failed to list sets: {e}")
            return self._error_response(f"Failed to list sets: {e}")

    def _handle_list_snapshots(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LIST_SNAPSHOTS command - list snapshots for a set."""
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        try:
            snapshots = self.storage.list_snapshots(set_name)
            return {
                "status": "ok",
                "snapshots": [s.to_dict() for s in snapshots],
            }
        except Exception as e:
            logger.error(f"Failed to list snapshots for '{set_name}': {e}")
            return self._error_response(f"Failed to list snapshots: {e}")

    def _handle_delete_set(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DELETE_SET command - delete a backup set and all its data.
        
        Removes:
        - C and O snapshot directories
        - All diff archives
        - The set's base directory
        """
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        logger.info(f"Deleting backup set '{set_name}'")
        
        try:
            result = self.storage.delete_set(set_name)
            
            return {
                "status": "ok",
                "message": f"Backup set '{set_name}' deleted successfully",
                "details": result,
            }
        except Exception as e:
            logger.error(f"Failed to delete backup set '{set_name}': {e}")
            return self._error_response(f"Failed to delete backup set: {e}")

    def _handle_list_files(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LIST_FILES command - list files in a snapshot."""
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        
        snapshot = request.get("snapshot", "C")
        path = request.get("path", "/")
        
        try:
            files = self.storage.list_files(set_name, snapshot, path)
            return {
                "status": "ok",
                "files": files,
            }
        except Exception as e:
            logger.error(
                f"Failed to list files for '{set_name}/{snapshot}/{path}': {e}"
            )
            return self._error_response(f"Failed to list files: {e}")

    def _handle_show_set(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SHOW_SET command - return parsed set.log entries."""
        set_name = request.get("set_name")
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")

        try:
            # Use storage._load_set_log() to retrieve entries (list newest-first)
            entries = self.storage._load_set_log(set_name)
            # Load set metadata (source paths) if available
            set_path = self.storage.get_set_path(set_name)
            metadata_path = set_path / "metadata.yaml"
            sources = None
            if metadata_path.exists():
                try:
                    import yaml as _yaml
                    with open(metadata_path, "r") as f:
                        md = _yaml.safe_load(f) or {}
                    sources = md.get("source_paths") or md.get("sources") or md.get("source")
                except Exception:
                    sources = None

            return {"status": "ok", "entries": entries, "source_paths": sources}
        except Exception as e:
            logger.error(f"Failed to load set.log for '{set_name}': {e}")
            return self._error_response(f"Failed to load set.log: {e}")

    def _handle_files_diff(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle FILES_DIFF command - compare local file metadata against backup history."""
        set_name = request.get("set_name")
        folder_path = request.get("folder_path")
        local_metadata = request.get("local_metadata")
        source_path = request.get("source_path")
        
        if not set_name:
            return self._error_response("Missing 'set_name' parameter")
        if not folder_path:
            return self._error_response("Missing 'folder_path' parameter")
        if not local_metadata:
            return self._error_response("Missing 'local_metadata' parameter")
        
        logger.info(f"Comparing files for '{folder_path}' in set '{set_name}'")
        # Log received local metadata to aid debugging (writes to info.log)
        try:
            logger.info(
                "Received local_metadata: %s",
                json.dumps({k: v for k, v in (local_metadata or {}).items()}, sort_keys=True),
            )
        except Exception:
            # Fallback: log basic summary
            try:
                logger.info("Received local_metadata with %d entries", len(local_metadata or {}))
            except Exception:
                logger.info("Received local_metadata (could not serialize details)")
        
        try:
            differences = self.storage.compare_files_across_backups(
                set_name, folder_path, local_metadata, source_path=source_path
            )
            
            return {
                "status": "ok",
                "differences": differences,
                "folder_path": folder_path,
            }
        except Exception as e:
            logger.error(f"Failed to compare files: {e}")
            return self._error_response(f"Failed to compare files: {e}")

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _error_response(self, message: str) -> Dict[str, Any]:
        """Create a standardized error response."""
        return {
            "status": "error",
            "message": message,
        }
