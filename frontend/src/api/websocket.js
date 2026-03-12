/**
 * WebSocket client for real-time scan progress.
 */

class WSClient {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
    this.isConnecting = false;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) return;
    this.isConnecting = true;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.isConnecting = false;
      this._emit('connected', true);
      // Start heartbeat
      this._heartbeat = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'pong') return;
        this._emit(data.type, data);
        this._emit('message', data);
      } catch {
        // ignore parse errors
      }
    };

    this.ws.onclose = () => {
      this.isConnecting = false;
      clearInterval(this._heartbeat);
      this._emit('connected', false);
      // Auto-reconnect after 3 seconds
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onerror = () => {
      this.isConnecting = false;
    };
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    clearInterval(this._heartbeat);
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(callback);
    return () => this.listeners.get(event)?.delete(callback);
  }

  _emit(event, data) {
    this.listeners.get(event)?.forEach((cb) => {
      try {
        cb(data);
      } catch {
        // prevent listener errors from breaking the ws
      }
    });
  }
}

export const wsClient = new WSClient();
