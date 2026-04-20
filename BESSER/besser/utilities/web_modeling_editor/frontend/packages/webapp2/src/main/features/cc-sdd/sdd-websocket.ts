/**
 * CC-SDD WebSocket Service for webapp2
 * Handles real-time communication with the SDD pipeline server.
 */

import { SDD_WS_URL } from '../../shared/constants/constant';

export type SDDMessageType =
  | 'connected'
  | 'pipeline_status'
  | 'file_update'
  | 'canvas_update'
  | 'agent_message'
  | 'pipeline_complete'
  | 'file_content'
  | 'error'
  | 'directory_status'
  | 'pong';

export interface SDDMessage {
  type: SDDMessageType;
  phase?: string;
  status?: string;
  message?: string;
  filename?: string;
  content?: string;
  canvasJson?: any;
  projectName?: string;
  files?: string[];
  has_files?: boolean;
}

type MessageHandler = (msg: SDDMessage) => void;

export class SDDWebSocketService {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 2000;
  private _isConnected = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        resolve();
        return;
      }

      try {
        this.ws = new WebSocket(SDD_WS_URL);

        this.ws.onopen = () => {
          this._isConnected = true;
          this.reconnectAttempts = 0;
          console.log('[SDD-WS] Connected to CC-SDD server');
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const msg: SDDMessage = JSON.parse(event.data);
            this._dispatch(msg.type, msg);
            this._dispatch('*', msg);
          } catch (e) {
            console.warn('[SDD-WS] Failed to parse message:', e);
          }
        };

        this.ws.onclose = (event) => {
          this._isConnected = false;
          console.log(`[SDD-WS] Disconnected (code: ${event.code})`);
          this._dispatch('disconnected', { type: 'error' as SDDMessageType, message: 'Disconnected from server' });

          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
            console.log(`[SDD-WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})...`);
            setTimeout(() => this.connect().catch(() => {}), delay);
          }
        };

        this.ws.onerror = (error) => {
          console.error('[SDD-WS] WebSocket error:', error);
          reject(new Error('WebSocket connection failed'));
        };
      } catch (e) {
        reject(e);
      }
    });
  }

  disconnect(): void {
    this.maxReconnectAttempts = 0;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this._isConnected = false;
  }

  send(data: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[SDD-WS] Cannot send — not connected');
      return;
    }
    this.ws.send(JSON.stringify(data));
  }

  startPipeline(idea: string, apiKey: string, outputDir?: string): void {
    this.send({ type: 'start_pipeline', idea, apiKey, outputDir: outputDir || '' });
  }

  sendVibeMessage(message: string): void {
    this.send({ type: 'vibe_message', message });
  }

  sendDiagramUpdate(canvasJson: any): void {
    this.send({ type: 'update_diagram', canvasJson });
  }

  requestFile(filename: string): void {
    this.send({ type: 'get_file', filename });
  }

  checkDirectory(outputDir: string): void {
    this.send({ type: 'check_directory', outputDir });
  }

  on(type: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);
    return () => {
      this.handlers.get(type)?.delete(handler);
    };
  }

  off(type: string, handler: MessageHandler): void {
    this.handlers.get(type)?.delete(handler);
  }

  private _dispatch(type: string, msg: SDDMessage): void {
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(msg);
        } catch (e) {
          console.error(`[SDD-WS] Handler error for '${type}':`, e);
        }
      });
    }
  }
}

export const sddWebSocket = new SDDWebSocketService();
