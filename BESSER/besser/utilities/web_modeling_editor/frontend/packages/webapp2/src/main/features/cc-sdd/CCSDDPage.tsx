/**
 * CCSDDPage — Main CC-SDD (Spec-Driven Development) page component for webapp2.
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
import { useAppDispatch } from '../../app/store/hooks';
import { switchDiagramTypeThunk, updateDiagramModelThunk } from '../../app/store/workspaceSlice';
import { sddWebSocket, SDDMessage } from './sdd-websocket';
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
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) =>
      `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`)
    .replace(/^---$/gm, '<hr/>')
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- \[x\] (.+)$/gm, '<li><input type="checkbox" checked disabled/> $1</li>')
    .replace(/^- \[ \] (.+)$/gm, '<li><input type="checkbox" disabled/> $1</li>')
    .replace(/^\* (.+)$/gm, '<li>$1</li>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // Tables
  html = html.replace(
    /(\|.+\|[\r\n]+\|[\s:|-]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)/g,
    (tableBlock) => {
      const rows = tableBlock.trim().split('\n').filter(r => r.trim());
      if (rows.length < 2) return tableBlock;
      const headerCells = rows[0].split('|').filter(c => c.trim());
      const dataRows = rows.slice(2);
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

  // Paragraphs
  html = html.split('\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';
    if (trimmed.startsWith('<')) return line;
    return `<p>${line}</p>`;
  }).join('\n');

  return html;
}

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

const FILE_DEFS: Omit<ProjectFile, 'content' | 'status'>[] = [
  { name: 'brief.md', icon: '📝' },
  { name: 'requirements.md', icon: '📋' },
  { name: 'design.md', icon: '🏗️' },
  { name: 'traceability.md', icon: '🔗' },
];

// ══════════════════════════════════════════════════════════════════════
// Component
// ══════════════════════════════════════════════════════════════════════

interface CCSDDPageProps {
  onClose?: () => void;
}

export const CCSDDPage: React.FC<CCSDDPageProps> = ({ onClose }) => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();

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
        // Update pipeline icon status
        setPhases(prev => prev.map(p =>
          p.id === msg.phase
            ? { ...p, status: msg.status as any }
            : p
        ));
        // Update corresponding file status to 'generating' if it is running
        if (msg.status === 'running' && msg.phase) {
          setFiles(prev => {
            const updated = new Map(prev);
            const fileName = `${msg.phase}.md`;
            const file = updated.get(fileName);
            if (file && file.status === 'pending') {
              updated.set(fileName, { ...file, status: 'generating' });
            }
            return updated;
          });
        }
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

  // ── Connect WebSocket ───────────────────────────────────────────────
  useEffect(() => {
    const unsub = sddWebSocket.on('*', handleWsMessage);
    sddWebSocket.connect().catch(err => {
      console.warn('[CC-SDD] WebSocket connection failed (will retry):', err);
    });
    return () => { unsub(); };
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

    const initialFiles = new Map<string, ProjectFile>();
    FILE_DEFS.forEach(f => {
      initialFiles.set(f.name, { ...f, status: 'pending', content: '' });
    });
    setFiles(initialFiles);

    // If perfectly disconnected, fail immediately.
    if (!sddWebSocket.isConnected) {
      setChatMessages([{
        id: 'error-ws',
        type: 'error',
        text: '❌ Connection to the CC-SDD AI Server is closed! Please ensure `python -m besser.utilities.ai_sdd.server` is running on port 8766.',
        timestamp: Date.now(),
      }]);
      setPhases(prev => prev.map(p => ({ ...p, status: 'error' })));
      setIsSending(false);
      return;
    }

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
    setTimeout(() => setIsSending(false), 30000);
  }, [chatInput, isSending]);

  useEffect(() => {
    const unsub = sddWebSocket.on('agent_message', (msg) => {
      if (msg.phase === 'vibe') setIsSending(false);
    });
    return unsub;
  }, []);

  // ── Export to Canvas ────────────────────────────────────────────────
  const handleExportToCanvas = useCallback(async () => {
    if (!canvasJson) return;
    
    // Switch the workspace to ClassDiagram first ensuring the correct editor maps it
    await dispatch(switchDiagramTypeThunk({ diagramType: 'ClassDiagram' }));
    
    // Overwrite the diagram model in Redux
    await dispatch(updateDiagramModelThunk({ model: canvasJson }));
    
    // Close the sidebar to reveal the canvas
    if (onClose) onClose();
  }, [canvasJson, dispatch, onClose]);

  const handleChatKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendVibeMessage();
    }
  }, [handleSendVibeMessage]);

  // ══════════════════════════════════════════════════════════════════
  // Render
  // ══════════════════════════════════════════════════════════════════

  if (!pipelineStarted) {
    return (
      <div className="flex flex-col h-full bg-background text-foreground overflow-hidden">
        <div className="flex items-center justify-between p-3 border-b border-border bg-card">
          <div className="flex items-center gap-3">
            <button
              className="p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground rounded-md transition-colors"
              onClick={() => (onClose ? onClose() : navigate('/'))}
              title="Close CC-SDD Studio"
            >
              ✕
            </button>
            <div className="font-bold flex items-center gap-1.5 text-primary">
              <span>⚡</span> CC-SDD
            </div>
          </div>
        </div>

        <div className="flex flex-col flex-1 items-center justify-center p-8 text-center overflow-y-auto">
          <div className="max-w-xl w-full">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-primary to-purple-500 bg-clip-text text-transparent mb-2">
              CC-SDD Studio
            </h1>
            <h2 className="text-muted-foreground mb-8">
              Spec-Driven Development — From Idea to Design in Minutes
            </h2>

            <div className="bg-card border border-border rounded-lg p-5 text-left mb-6 shadow-sm">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">
                🔑 Gemini API Key
              </label>
              <input
                type="password"
                className="w-full px-3 py-2 bg-background border border-border rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="AIzaSy..."
                id="sdd-api-key-input"
              />
              <div className={`text-xs mt-2 ${apiKeyValid ? 'text-emerald-500' : 'text-amber-500'}`}>
                {apiKeyValid ? '✅ API key configured' : '⚠️ Enter a valid Gemini API key to continue'}
              </div>
            </div>

            <div className="w-full">
              <textarea
                className="w-full min-h-[120px] p-4 bg-card border border-border rounded-lg text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary/50 mb-4 shadow-sm"
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder={'Describe your software idea...\n\nExample: "I want to build an e-commerce platform with user accounts, product catalog, shopping cart..."'}
                id="sdd-idea-input"
                disabled={!apiKeyValid}
              />
              <button
                className="w-full py-3 bg-gradient-to-r from-primary to-purple-600 hover:from-primary/90 hover:to-purple-600/90 text-white font-semibold rounded-md shadow-md disabled:opacity-50 disabled:cursor-not-allowed transition-all"
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

  const activeFileData = activeFile ? files.get(activeFile) : null;

  return (
    <div className="flex flex-col h-full bg-background text-foreground overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3">
          <button
            className="p-1 text-muted-foreground hover:bg-accent hover:text-foreground rounded-md transition-colors"
            onClick={() => (onClose ? onClose() : navigate('/'))}
            title="Close Studio"
          >
            ✕
          </button>
          <div className="font-bold flex items-center gap-1.5 text-primary">
            <span>⚡</span> CC-SDD
          </div>
          {projectName && (
            <span className="px-2.5 py-0.5 bg-muted/50 border border-border rounded-full text-xs text-muted-foreground">
              {projectName}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canvasJson && (
            <button
              className="px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-md text-xs font-semibold transition-colors flex items-center gap-1.5"
              onClick={handleExportToCanvas}
              id="sdd-export-canvas"
            >
              <span>🎨</span> Export to Canvas
            </button>
          )}
          <button
            className="px-3 py-1.5 bg-card hover:bg-accent border border-border rounded-md text-xs font-medium transition-colors"
            onClick={() => setPipelineStarted(false)}
            id="sdd-new-project"
          >
            + New
          </button>
        </div>
      </div>

      {/* Main Sidebar Layout */}
      <div className="flex flex-col flex-1 min-h-0">
        
        {/* Horizontal Pipeline Status */}
        <div className="flex flex-row items-center gap-2 overflow-x-auto p-3 border-b border-border bg-muted/20 shrink-0">
          <div className="text-[10px] uppercase font-bold text-muted-foreground mr-1 shrink-0">Pipeline</div>
          {phases.map((phase, idx) => (
            <div key={phase.id} className="flex items-center shrink-0">
              <div
                className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs whitespace-nowrap transition-colors ${
                  phase.status === 'active' || phase.status === 'running'
                    ? 'bg-primary/10 border-primary/30 text-primary'
                    : phase.status === 'completed'
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                    : phase.status === 'error'
                    ? 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400'
                    : 'bg-card border-border text-muted-foreground'
                }`}
              >
                <span>
                  {phase.status === 'completed' ? '✓' : phase.status === 'running' ? '⟳' : phase.status === 'error' ? '✕' : phase.icon}
                </span>
                <span className="font-medium">{phase.label}</span>
              </div>
              {idx < phases.length - 1 && <div className="w-4 h-px bg-border mx-1" />}
            </div>
          ))}
        </div>

        {/* File Explorer */}
        <div className="flex flex-col border-b border-border shrink-0 max-h-[30%] bg-card">
          <div className="p-2.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider border-b border-border bg-muted/10">
            📂 Explorer
          </div>
          <div className="overflow-y-auto p-1.5 space-y-0.5">
            {Array.from(files.values()).map((file) => (
              <button
                key={file.name}
                onClick={() => file.status === 'ready' && setActiveFile(file.name)}
                className={`w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-md text-sm transition-colors text-left ${
                  activeFile === file.name
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'hover:bg-accent text-foreground'
                } ${file.status !== 'ready' ? 'opacity-70 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <div className="flex items-center gap-2 truncate">
                  <span>{file.icon}</span>
                  <span className="truncate">{file.name}</span>
                </div>
                {file.status !== 'ready' && (
                  <span className="text-[10px] font-bold text-amber-500 bg-amber-500/10 px-1.5 py-0.5 rounded-sm shrink-0">
                    {file.status === 'generating' ? '⟳ GEN' : 'WAIT'}
                  </span>
                )}
                {file.status === 'ready' && activeFile === file.name && (
                  <span className="text-primary font-bold">✓</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Vibe Modeling Chat */}
        <div className="flex flex-col flex-1 min-h-0 bg-background relative">
          <div className="p-2 border-b border-border bg-muted/20 text-xs font-semibold text-foreground flex items-center justify-between">
            <span>💬 {pipelineComplete ? 'Vibe Modeling' : 'Pipeline Log'}</span>
            {pipelineComplete && (
              <span className="bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 text-[10px] rounded animate-pulse">
                LIVE
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {chatMessages.map((msg) => (
              <div
                key={msg.id}
                className={`p-2.5 rounded-lg text-sm max-w-[95%] break-words ${
                  msg.type === 'user'
                    ? 'bg-primary text-primary-foreground self-end ml-auto rounded-tr-sm'
                    : msg.type === 'system'
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
                    : msg.type === 'error'
                    ? 'bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20'
                    : 'bg-card border border-border text-foreground self-start mr-auto rounded-tl-sm'
                }`}
                dangerouslySetInnerHTML={{ __html: renderChatMd(msg.text) }}
              />
            ))}
            <div ref={chatEndRef} />
          </div>

          {pipelineComplete && (
            <div className="p-3 border-t border-border bg-card shrink-0">
              <div className="flex items-end gap-2 bg-background border border-border rounded-md focus-within:ring-1 focus-within:ring-primary/50 overflow-hidden pr-1">
                <textarea
                  ref={chatInputRef}
                  className="w-full max-h-32 min-h-[36px] bg-transparent text-sm p-2 resize-none focus:outline-none"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={handleChatKeyDown}
                  placeholder={'Instruct the agent...\n(e.g. "Add email to User")'}
                  rows={2}
                  disabled={isSending}
                />
                <button
                  className="mb-1.5 mr-1 p-1.5 text-primary hover:bg-primary/10 rounded-md transition-colors disabled:opacity-50"
                  onClick={handleSendVibeMessage}
                  disabled={!chatInput.trim() || isSending}
                >
                  {isSending ? '⟳' : '➤'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Floating Canvas Overlay for Markdown Viewing */}
      {activeFile && (
        <div className="fixed top-[56px] bottom-0 left-[506px] right-0 z-20 bg-background border-l border-border shadow-2xl flex flex-col pointer-events-auto animate-in slide-in-from-right-4 duration-300">
          <div className="flex items-center px-4 bg-muted/20 border-b border-border shrink-0 min-h-[48px]">
            <div className="flex items-center bg-card border border-border border-b-0 mt-2 px-3 py-1.5 rounded-t-md text-sm font-medium text-primary">
              <span className="mr-2">{activeFileData?.icon}</span>
              {activeFile}
              <button
                className="ml-3 p-0.5 rounded-sm hover:bg-accent text-muted-foreground hover:text-foreground"
                onClick={(e) => { e.stopPropagation(); setActiveFile(null); }}
                title="Close file viewer"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-8">
            {canvasJson && activeFile === 'design.md' && (
              <div className="mb-6 p-4 bg-primary/10 border border-primary/20 rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">🎨</span>
                  <div>
                    <h3 className="text-primary font-semibold">BUML Class Diagram Ready</h3>
                    <p className="text-sm text-foreground/80">You can export this to your BESSER workspace to continue modeling manually.</p>
                  </div>
                </div>
                <button
                  className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md font-medium shadow-sm"
                  onClick={(e) => {
                    handleExportToCanvas();
                    // Auto-close viewer when exported so user can see the canvas immediately
                    setActiveFile(null); 
                  }}
                >
                  Export to Canvas →
                </button>
              </div>
            )}

            {activeFileData && activeFileData.content ? (
              <div
                className="sdd-md-viewer"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(activeFileData.content) }}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <span className="text-4xl mb-4">📄</span>
                <p>Generating document content...</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );

};

export default CCSDDPage;
