/**
 * CCSDDPage — Main CC-SDD (Spec-Driven Development) page component.
 *
 * Orchestrates the entire SDD workflow:
 * 1. API key configuration
 * 2. Idea input
 * 3. Pipeline execution with real-time feedback
 * 4. File explorer + Markdown viewer
 * 5. Vibe Modeling chat + Canvas integration
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { sddWebSocket, SDDMessage } from './services/sdd-websocket';
import './cc-sdd.css';

// ── Types ──────────────────────────────────────────────────────────────

interface PipelinePhase {
  id: string;
  label: string;
  icon: string;
  status: 'pending' | 'running' | 'completed' | 'error';
}

interface ChatMessage {
  id: string;
  type: 'agent' | 'user' | 'system' | 'error';
  text: string;
  phase?: string;
  timestamp: number;
}

interface ProjectFile {
  name: string;
  icon: string;
  status: 'pending' | 'generating' | 'ready';
  content: string;
}

// ── Markdown Renderer ──────────────────────────────────────────────────

function renderMarkdown(md: string): string {
  if (!md) return '';
  let html = md
    // Escape HTML
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Code blocks (fenced)
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) =>
      `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`)
    // Horizontal rules
    .replace(/^---$/gm, '<hr/>')
    // Headers
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // Bold and italic
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Checkboxes
    .replace(/^- \[x\] (.+)$/gm, '<li><input type="checkbox" checked disabled/> $1</li>')
    .replace(/^- \[ \] (.+)$/gm, '<li><input type="checkbox" disabled/> $1</li>')
    // Unordered list items
    .replace(/^\* (.+)$/gm, '<li>$1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    // Blockquotes
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Tables
  html = html.replace(
    /(\|.+\|[\r\n]+\|[\s:|-]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)/g,
    (tableBlock) => {
      const rows = tableBlock.trim().split('\n').filter(r => r.trim());
      if (rows.length < 2) return tableBlock;
      const headerCells = rows[0].split('|').filter(c => c.trim());
      const dataRows = rows.slice(2); // Skip separator row
      let table = '<table><thead><tr>';
      headerCells.forEach(cell => { table += `<th>${cell.trim()}</th>`; });
      table += '</tr></thead><tbody>';
      dataRows.forEach(row => {
        const cells = row.split('|').filter(c => c.trim());
        table += '<tr>';
        cells.forEach(cell => { table += `<td>${cell.trim()}</td>`; });
        table += '</tr>';
      });
      table += '</tbody></table>';
      return table;
    }
  );

  // Wrap loose list items
  html = html.replace(/(<li>[\s\S]*?<\/li>)/g, (match) => {
    // Check if already inside a list
    return match;
  });

  // Paragraphs (simple: non-html lines)
  html = html.split('\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';
    if (trimmed.startsWith('<')) return line;
    return `<p>${line}</p>`;
  }).join('\n');

  return html;
}

// ── Simple chat markdown (for messages) ────────────────────────────────

function renderChatMd(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br/>');
}

// ── Initial pipeline phases ────────────────────────────────────────────

const INITIAL_PHASES: PipelinePhase[] = [
  { id: 'brief', label: 'Brief', icon: '📝', status: 'pending' },
  { id: 'requirements', label: 'Requirements', icon: '📋', status: 'pending' },
  { id: 'design', label: 'Design (BUML)', icon: '🏗️', status: 'pending' },
  { id: 'traceability', label: 'Traceability', icon: '🔗', status: 'pending' },
];

// ── File definitions ───────────────────────────────────────────────────

const FILE_DEFS: Omit<ProjectFile, 'content' | 'status'>[] = [
  { name: 'brief.md', icon: '📝' },
  { name: 'requirements.md', icon: '📋' },
  { name: 'design.md', icon: '🏗️' },
  { name: 'traceability.md', icon: '🔗' },
];

// ══════════════════════════════════════════════════════════════════════
// Component
// ══════════════════════════════════════════════════════════════════════

export const CCSDDPage: React.FC = () => {
  const navigate = useNavigate();

  // ── State ──────────────────────────────────────────────────────────
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('sdd_gemini_api_key') || '');
  const [apiKeyValid, setApiKeyValid] = useState(false);
  const [idea, setIdea] = useState('');
  const [pipelineStarted, setPipelineStarted] = useState(false);
  const [pipelineComplete, setPipelineComplete] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [phases, setPhases] = useState<PipelinePhase[]>(INITIAL_PHASES);
  const [files, setFiles] = useState<Map<string, ProjectFile>>(new Map());
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [canvasJson, setCanvasJson] = useState<any>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  // ── API Key validation ─────────────────────────────────────────────
  useEffect(() => {
    const valid = apiKey.trim().length > 20 && apiKey.startsWith('AIza');
    setApiKeyValid(valid);
    if (valid) {
      localStorage.setItem('sdd_gemini_api_key', apiKey);
    }
  }, [apiKey]);

  // ── Auto-scroll chat ────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // ── WebSocket message handler ───────────────────────────────────────
  const handleWsMessage = useCallback((msg: SDDMessage) => {
    switch (msg.type) {
      case 'pipeline_status':
        setPhases(prev => prev.map(p =>
          p.id === msg.phase
            ? { ...p, status: msg.status as any }
            : p
        ));
        break;

      case 'file_update':
        if (msg.filename && msg.content !== undefined) {
          setFiles(prev => {
            const updated = new Map(prev);
            const def = FILE_DEFS.find(f => f.name === msg.filename);
            updated.set(msg.filename!, {
              name: msg.filename!,
              icon: def?.icon || '📄',
              status: 'ready',
              content: msg.content!,
            });
            return updated;
          });
          // Auto-open the first generated file
          setActiveFile(prev => prev || msg.filename!);
        }
        break;

      case 'canvas_update':
        if (msg.canvasJson) {
          setCanvasJson(msg.canvasJson);
        }
        break;

      case 'agent_message':
        setChatMessages(prev => [...prev, {
          id: `agent-${Date.now()}-${Math.random()}`,
          type: msg.phase === 'vibe' ? 'agent' : 'system',
          text: msg.message || '',
          phase: msg.phase,
          timestamp: Date.now(),
        }]);
        break;

      case 'pipeline_complete':
        setPipelineComplete(true);
        if (msg.projectName) setProjectName(msg.projectName);
        break;

      case 'error':
        setChatMessages(prev => [...prev, {
          id: `error-${Date.now()}`,
          type: 'error',
          text: msg.message || 'An error occurred',
          phase: msg.phase,
          timestamp: Date.now(),
        }]);
        setIsSending(false);
        break;
    }
  }, []);

  // ── Connect WebSocket and register handlers ─────────────────────────
  useEffect(() => {
    const unsub = sddWebSocket.on('*', handleWsMessage);
    sddWebSocket.connect().catch(err => {
      console.warn('[CC-SDD] WebSocket connection failed (will retry):', err);
    });
    return () => {
      unsub();
    };
  }, [handleWsMessage]);

  // ── Start Pipeline ──────────────────────────────────────────────────
  const handleStartPipeline = useCallback(() => {
    if (!apiKeyValid || !idea.trim()) return;

    setPipelineStarted(true);
    setPhases(INITIAL_PHASES);
    setFiles(new Map());
    setActiveFile(null);
    setChatMessages([{
      id: 'start',
      type: 'user',
      text: idea.trim(),
      timestamp: Date.now(),
    }]);
    setPipelineComplete(false);
    setCanvasJson(null);

    // Initialize file placeholders
    const initialFiles = new Map<string, ProjectFile>();
    FILE_DEFS.forEach(f => {
      initialFiles.set(f.name, { ...f, status: 'pending', content: '' });
    });
    setFiles(initialFiles);

    sddWebSocket.startPipeline(idea.trim(), apiKey);
  }, [apiKeyValid, idea, apiKey]);

  // ── Send Vibe Message ───────────────────────────────────────────────
  const handleSendVibeMessage = useCallback(() => {
    const msg = chatInput.trim();
    if (!msg || isSending) return;

    setChatMessages(prev => [...prev, {
      id: `user-${Date.now()}`,
      type: 'user',
      text: msg,
      timestamp: Date.now(),
    }]);

    setIsSending(true);
    sddWebSocket.sendVibeMessage(msg);
    setChatInput('');

    // Reset sending state after timeout (safety)
    setTimeout(() => setIsSending(false), 30000);
  }, [chatInput, isSending]);

  // Clear sending state when agent responds
  useEffect(() => {
    const unsub = sddWebSocket.on('agent_message', (msg) => {
      if (msg.phase === 'vibe') {
        setIsSending(false);
      }
    });
    return unsub;
  }, []);

  // ── Export to Canvas ────────────────────────────────────────────────
  const handleExportToCanvas = useCallback(() => {
    if (!canvasJson) return;

    // Store the canvas JSON in localStorage for the editor to pick up
    localStorage.setItem('sdd_canvas_import', JSON.stringify(canvasJson));
    // Navigate to main editor
    navigate('/');
    // Dispatch a custom event so the editor knows to import
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('sdd-canvas-import', { detail: canvasJson }));
    }, 500);
  }, [canvasJson, navigate]);

  // ── Key handler for chat input ──────────────────────────────────────
  const handleChatKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendVibeMessage();
    }
  }, [handleSendVibeMessage]);

  // ══════════════════════════════════════════════════════════════════
  // Render
  // ══════════════════════════════════════════════════════════════════

  // ── Welcome Screen (before pipeline starts) ─────────────────────
  if (!pipelineStarted) {
    return (
      <div className="sdd-page">
        <div className="sdd-header">
          <div className="sdd-header-left">
            <button className="sdd-btn sdd-btn-back" onClick={() => navigate('/')} title="Back to Editor">
              ←
            </button>
            <div className="sdd-logo">
              <span className="sdd-logo-icon">⚡</span>
              CC-SDD
            </div>
          </div>
        </div>

        <div className="sdd-welcome">
          <div className="sdd-welcome-content">
            <h1>CC-SDD Studio</h1>
            <h2>Spec-Driven Development — From Idea to Design in Minutes</h2>

            {/* API Key Config */}
            <div className="sdd-api-key-section">
              <label>🔑 Gemini API Key</label>
              <div className="sdd-input-group">
                <input
                  type="password"
                  className="sdd-input"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="AIzaSy..."
                  id="sdd-api-key-input"
                />
              </div>
              <div className={`sdd-api-status ${apiKeyValid ? 'valid' : ''}`}>
                {apiKeyValid ? '✅ API key configured' : '⚠️ Enter a valid Gemini API key to continue'}
              </div>
            </div>

            {/* Idea Input */}
            <div className="sdd-idea-section">
              <textarea
                className="sdd-textarea"
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder="Describe your software idea... &#10;&#10;Example: &quot;I want to build an e-commerce platform with user accounts, product catalog, shopping cart, order processing, and payment integration. Admins should manage inventory and users should track orders.&quot;"
                id="sdd-idea-input"
                disabled={!apiKeyValid}
              />
              <button
                className="sdd-btn sdd-btn-primary sdd-start-btn"
                onClick={handleStartPipeline}
                disabled={!apiKeyValid || !idea.trim()}
                id="sdd-start-pipeline"
              >
                🚀 Generate Spec &amp; Design
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Workspace (after pipeline starts) ──────────────────────────
  const activeFileData = activeFile ? files.get(activeFile) : null;

  return (
    <div className="sdd-page">
      {/* Header */}
      <div className="sdd-header">
        <div className="sdd-header-left">
          <button className="sdd-btn sdd-btn-back" onClick={() => navigate('/')} title="Back to Editor">
            ←
          </button>
          <div className="sdd-logo">
            <span className="sdd-logo-icon">⚡</span>
            CC-SDD
          </div>
          {projectName && <span className="sdd-project-name">{projectName}</span>}
        </div>
        <div className="sdd-header-actions">
          {canvasJson && (
            <button className="sdd-btn sdd-btn-primary" onClick={handleExportToCanvas} id="sdd-export-canvas">
              🎨 Export BUML to Canvas
            </button>
          )}
          <button className="sdd-btn" onClick={() => { setPipelineStarted(false); }} id="sdd-new-project">
            + New Project
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="sdd-body">
        <div className="sdd-workspace">
          {/* Left Panel — File Explorer + Pipeline */}
          <div className="sdd-file-explorer">
            {/* Pipeline Status */}
            <div className="sdd-pipeline-section">
              <div className="sdd-pipeline-title">Pipeline Status</div>
              <div className="sdd-pipeline-steps">
                {phases.map((phase, idx) => (
                  <React.Fragment key={phase.id}>
                    <div className={`sdd-pipeline-step ${phase.status}`}>
                      <div className="sdd-step-indicator">
                        {phase.status === 'completed' ? '✓' :
                         phase.status === 'running' ? '⟳' :
                         phase.status === 'error' ? '✕' :
                         (idx + 1)}
                      </div>
                      <span className="sdd-step-label">{phase.icon} {phase.label}</span>
                    </div>
                    {idx < phases.length - 1 && <div className="sdd-step-connector" />}
                  </React.Fragment>
                ))}
              </div>
            </div>

            {/* File Tree */}
            <div className="sdd-explorer-header">📂 Explorer — {projectName || 'Project'}</div>
            <div className="sdd-file-tree">
              {Array.from(files.values()).map(file => (
                <div
                  key={file.name}
                  className={`sdd-file-item ${activeFile === file.name ? 'active' : ''}`}
                  onClick={() => file.status === 'ready' && setActiveFile(file.name)}
                  id={`sdd-file-${file.name.replace('.', '-')}`}
                >
                  <span className="sdd-file-icon">{file.icon}</span>
                  <span className="sdd-file-name">{file.name}</span>
                  {file.status !== 'ready' && (
                    <span className={`sdd-file-status ${file.status}`}>
                      {file.status === 'generating' ? '⟳' : '•••'}
                    </span>
                  )}
                  {file.status === 'ready' && (
                    <span className="sdd-file-status ready">✓</span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Center — Content Viewer */}
          <div className="sdd-main-content">
            {/* Tab bar */}
            {activeFile && (
              <div className="sdd-content-tabs">
                {Array.from(files.values())
                  .filter(f => f.status === 'ready')
                  .map(file => (
                    <div
                      key={file.name}
                      className={`sdd-tab ${activeFile === file.name ? 'active' : ''}`}
                      onClick={() => setActiveFile(file.name)}
                    >
                      {file.icon} {file.name}
                    </div>
                  ))}
              </div>
            )}

            <div className="sdd-content-area">
              {/* Canvas export banner */}
              {canvasJson && activeFile === 'design.md' && (
                <div className="sdd-canvas-banner">
                  🎨 BUML class diagram ready for canvas export
                  <button className="sdd-btn" onClick={handleExportToCanvas}>
                    Export to Canvas →
                  </button>
                </div>
              )}

              {/* Markdown content */}
              {activeFileData && activeFileData.content ? (
                <div
                  className="sdd-md-viewer"
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(activeFileData.content) }}
                />
              ) : (
                <div className="sdd-empty-state">
                  <div className="sdd-empty-state-icon">📄</div>
                  <h3>
                    {pipelineComplete
                      ? 'Select a file to view'
                      : 'Generating documents...'}
                  </h3>
                  <p>
                    {pipelineComplete
                      ? 'Click on a file in the explorer to view its contents.'
                      : 'The AI agents are working on your project. Documents will appear as they are generated.'}
                  </p>
                  {!pipelineComplete && <div className="sdd-spinner" style={{ marginTop: 16 }} />}
                </div>
              )}
            </div>
          </div>

          {/* Right Panel — Chat */}
          <div className="sdd-chat-panel">
            <div className="sdd-chat-header">
              💬 {pipelineComplete ? 'Vibe Modeling' : 'Pipeline Log'}
              {pipelineComplete && <span className="sdd-chat-badge">Live</span>}
            </div>

            <div className="sdd-chat-messages">
              {chatMessages.map(msg => (
                <div
                  key={msg.id}
                  className={`sdd-chat-msg ${msg.type}`}
                  dangerouslySetInnerHTML={{ __html: renderChatMd(msg.text) }}
                />
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* Chat input — only visible after pipeline completes */}
            {pipelineComplete && (
              <div className="sdd-chat-input-area">
                <div className="sdd-chat-input-wrapper">
                  <textarea
                    ref={chatInputRef}
                    className="sdd-chat-input"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={handleChatKeyDown}
                    placeholder="Modify diagram or requirements... &#10;e.g., &quot;Add an email attribute to User&quot;"
                    rows={1}
                    disabled={isSending}
                    id="sdd-vibe-input"
                  />
                  <button
                    className="sdd-chat-send"
                    onClick={handleSendVibeMessage}
                    disabled={!chatInput.trim() || isSending}
                    id="sdd-vibe-send"
                  >
                    {isSending ? <div className="sdd-spinner" /> : '➤'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CCSDDPage;
