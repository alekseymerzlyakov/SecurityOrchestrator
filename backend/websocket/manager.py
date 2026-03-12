"""WebSocket connection manager for real-time scan progress."""

import json
from typing import Any
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and broadcasts scan progress."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]):
        """Send a message to all connected clients."""
        data = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.remove(conn)

    async def send_scan_progress(
        self,
        scan_id: int,
        step_name: str,
        status: str,
        files_processed: int,
        total_files: int,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        findings_count: int = 0,
        message: str = "",
    ):
        """Broadcast scan progress update."""
        await self.broadcast({
            "type": "scan_progress",
            "scan_id": scan_id,
            "step_name": step_name,
            "status": status,
            "files_processed": files_processed,
            "total_files": total_files,
            "tokens_used": tokens_used,
            "cost_usd": cost_usd,
            "findings_count": findings_count,
            "message": message,
            "percent": round(files_processed / total_files * 100, 1) if total_files > 0 else 0,
        })

    async def send_finding(self, scan_id: int, finding: dict):
        """Broadcast a new finding in real-time."""
        await self.broadcast({
            "type": "new_finding",
            "scan_id": scan_id,
            "finding": finding,
        })

    async def send_scan_complete(self, scan_id: int, summary: dict):
        """Broadcast scan completion."""
        await self.broadcast({
            "type": "scan_complete",
            "scan_id": scan_id,
            "summary": summary,
        })


# Singleton instance
ws_manager = ConnectionManager()
