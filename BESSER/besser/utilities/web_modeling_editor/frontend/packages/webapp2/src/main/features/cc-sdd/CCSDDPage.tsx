/**
 * CCSDDPage — Main CC-SDD (Spec-Driven Development) page component for webapp2.
 *
 * Orchestrates the interactive SDD workflow:
 * 1. API key configuration
 * 2. Idea input
 * 3. Phase-by-phase pipeline with chat-based interaction (no buttons)
 * 4. File explorer + Markdown viewer
 * 5. Chat always active — agent determines intent (advance/iterate/vibe)
 * 6. Auto-renders diagram on canvas when design is generated
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../app/store/hooks';
import { switchDiagramTypeThunk, updateDiagramModelThunk, bumpEditorRevision, selectActiveDiagram } from '../../app/store/workspaceSlice';
import { ClassDiagramConverter } from '../assistant/services/converters/ClassDiagramConverter';
import { sddWebSocket, SDDMessage } from './sdd-websocket';
import './cc-sdd.css';

// ── Types ──────────────────────────────────────────────────────────────

interface PipelinePhase {
  id: string;
  label: string;
  icon: string;
  status: 'pending' | 'running' | 'completed' | 'ready' | 'error';
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
  { id: 'design', label: 'Design', icon: '🏗️', status: 'pending' },
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
  const [outputDir, setOutputDir] = useState(() => localStorage.getItem('sdd_output_dir') || '');
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
  const [hasPendingDiagramChanges, setHasPendingDiagramChanges] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [restoreStatus, setRestoreStatus] = useState<'idle' | 'checking' | 'found' | 'not_found'>('idle');
  const isSyncingRef = useRef(false);

  // Read the current diagram model from Redux (changes when user edits on canvas)
  const activeDiagram = useAppSelector(selectActiveDiagram);

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

  // ── Persist outputDir ───────────────────────────────────────────────
  useEffect(() => {
    if (outputDir.trim()) {
      localStorage.setItem('sdd_output_dir', outputDir.trim());
    }
  }, [outputDir]);

  const handleOutputDirChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setOutputDir(e.target.value);
    setRestoreStatus('idle');
  };

  const handleCheckRestore = useCallback(() => {
    if (!outputDir.trim() || !sddWebSocket.isConnected) return;
    setRestoreStatus('checking');
    sddWebSocket.checkDirectory(outputDir.trim());
  }, [outputDir]);

  // ── Auto-scroll chat ────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // ── Detect canvas diagram changes (bidirectional traceability) ──────
  useEffect(() => {
    // We only need the diagram model to track changes. It works even outside pipeline runs.
    if (!activeDiagram?.model) return;

    // Extract the current canvas state as SystemClassSpec
    const currentModel = activeDiagram.model;
    if (!currentModel || typeof currentModel !== 'object') return;

    try {
      const currentSpec = ClassDiagramConverter.reverseConvert(currentModel);

      if (!canvasJson) {
        // If we don't have a baseline yet, set the current model as the baseline immediately
        setCanvasJson(currentSpec);
        return;
      }

      // Quick comparison: class count + class names + attribute counts
      const baseClasses = new Set((canvasJson.classes || []).map((c: any) => c.className));
      const currentClasses = new Set((currentSpec.classes || []).map((c: any) => c.className));

      // Check for added/removed classes
      let hasChanges = baseClasses.size !== currentClasses.size;

      if (!hasChanges) {
        // Check if class names differ
        for (const name of currentClasses) {
          if (!baseClasses.has(name)) { hasChanges = true; break; }
        }
      }

      if (!hasChanges) {
        // Deep check: compare attribute counts per class
        const baseAttrCounts: Record<string, number> = {};
        (canvasJson.classes || []).forEach((c: any) => {
          baseAttrCounts[c.className] = (c.attributes || []).length;
        });
        for (const cls of currentSpec.classes || []) {
          const baseCount = baseAttrCounts[cls.className] ?? -1;
          if (baseCount !== (cls.attributes || []).length) {
            hasChanges = true;
            break;
          }
        }
      }

      if (!hasChanges) {
        // Check relationship count
        const baseRelCount = (canvasJson.relationships || []).length;
        const currentRelCount = (currentSpec.relationships || []).length;
        if (baseRelCount !== currentRelCount) hasChanges = true;
      }

      setHasPendingDiagramChanges(hasChanges);
      // Notify top bar about sync availability
      window.dispatchEvent(new CustomEvent('sdd:sync-available', { detail: { available: hasChanges } }));
    } catch (e) {
      console.warn('[CC-SDD] Change detection error:', e);
    }
  }, [activeDiagram?.model, canvasJson]);

  // ── Auto-render diagram on canvas when received ─────────────────────
  const autoRenderCanvas = useCallback(async (systemSpec: any) => {
    if (!systemSpec) return;
    try {
      // 1. Ensure we're on ClassDiagram
      await dispatch(switchDiagramTypeThunk({ diagramType: 'ClassDiagram' }));

      // 2. Convert SystemClassSpec → Apollon UMLModel via ConverterFactory
      const { ConverterFactory } = await import('../assistant/services/converters');
      const converter = ConverterFactory.getConverter('ClassDiagram');
      const umlModel = converter.convertCompleteSystem(systemSpec);

      // 3. Dispatch to Redux store and bump editor revision to force re-render
      await dispatch(updateDiagramModelThunk({ model: umlModel }));
      dispatch(bumpEditorRevision());

      console.log('[CC-SDD] Diagram auto-rendered:', systemSpec.classes?.length, 'classes');
    } catch (e) {
      console.warn('[CC-SDD] Auto-render to canvas failed:', e);
    }
  }, [dispatch]);

  // ── WebSocket message handler ───────────────────────────────────────
  const handleWsMessage = useCallback((msg: SDDMessage) => {
    switch (msg.type) {
      case 'pipeline_status':
        setPhases(prev => prev.map(p =>
          p.id === msg.phase
            ? { ...p, status: msg.status as any }
            : p
        ));
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
          // Auto-render diagram on the canvas immediately
          autoRenderCanvas(msg.canvasJson);
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
        setIsSending(false);
        // If we were syncing and this is a traceability message, sync is done
        if (isSyncingRef.current && msg.phase === 'traceability') {
          setIsSyncing(false);
          isSyncingRef.current = false;
          setHasPendingDiagramChanges(false);
        }
        break;

      case 'pipeline_complete':
        setPipelineComplete(true);
        if (msg.projectName) setProjectName(msg.projectName);
        break;

      case 'directory_status':
        setRestoreStatus(msg.has_files ? 'found' : 'not_found');
        break;

      case 'error':
        setRestoreStatus(prev => prev === 'checking' ? 'idle' : prev);
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
  }, [autoRenderCanvas]);

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
    if (!apiKeyValid) return;
    if (!idea.trim() && restoreStatus !== 'found') return;

    setPipelineStarted(true);
    setPhases(INITIAL_PHASES);
    setFiles(new Map());
    setActiveFile(null);
    setChatMessages([{
      id: 'start',
      type: 'user',
      text: idea.trim() || '📂 Restaurando proyecto...',
      timestamp: Date.now(),
    }]);
    setPipelineComplete(false);
    setCanvasJson(null);

    const initialFiles = new Map<string, ProjectFile>();
    FILE_DEFS.forEach(f => {
      initialFiles.set(f.name, { ...f, status: 'pending', content: '' });
    });
    setFiles(initialFiles);

    if (!sddWebSocket.isConnected) {
      setChatMessages([{
        id: 'error-ws',
        type: 'error',
        text: '❌ Connection to the CC-SDD AI Server is closed! Please ensure the SDD server is running on port 8766.',
        timestamp: Date.now(),
      }]);
      setPhases(prev => prev.map(p => ({ ...p, status: 'error' })));
      return;
    }

    sddWebSocket.startPipeline(idea.trim(), apiKey, outputDir.trim() || undefined);
  }, [apiKeyValid, idea, apiKey, outputDir]);

  // ── Send Chat Message (always active — agent decides intent) ────────
  const handleSendMessage = useCallback(() => {
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
  }, [chatInput, isSending]);

  // ── Sync Diagram Changes (Bidirectional Traceability) ──────────────
  const handleSyncDiagram = useCallback(() => {
    if (!activeDiagram?.model || isSyncing) return;

    try {
      const currentSpec = ClassDiagramConverter.reverseConvert(activeDiagram.model);
      setIsSyncing(true);
      isSyncingRef.current = true;

      // Notify user in chat
      setChatMessages(prev => [...prev, {
        id: `sync-${Date.now()}`,
        type: 'system',
        text: '🔄 **Sincronizando cambios del diagrama** con requisitos y trazabilidad...',
        phase: 'traceability',
        timestamp: Date.now(),
      }]);

      // Send to backend via WebSocket
      sddWebSocket.sendDiagramUpdate(currentSpec);

      // Update local baseline
      setCanvasJson(currentSpec);
    } catch (e) {
      console.error('[CC-SDD] Sync failed:', e);
      setChatMessages(prev => [...prev, {
        id: `sync-error-${Date.now()}`,
        type: 'error',
        text: `❌ Error al sincronizar: ${e}`,
        timestamp: Date.now(),
      }]);
      setIsSyncing(false);
      isSyncingRef.current = false;
    }
  }, [activeDiagram?.model, isSyncing]);

  // ── Listen for sync trigger from top bar ────────────────────────────
  useEffect(() => {
    const onTrigger = () => handleSyncDiagram();
    window.addEventListener('sdd:sync-trigger', onTrigger);
    return () => window.removeEventListener('sdd:sync-trigger', onTrigger);
  }, [handleSyncDiagram]);

  // ── Broadcast sync state changes ───────────────────────────────────
  useEffect(() => {
    if (!isSyncing && !hasPendingDiagramChanges) {
      window.dispatchEvent(new CustomEvent('sdd:sync-available', { detail: { available: false } }));
    }
  }, [isSyncing, hasPendingDiagramChanges]);

  useEffect(() => {
    if (isSyncing) {
      window.dispatchEvent(new CustomEvent('sdd:sync-syncing', { detail: { syncing: true } }));
    } else {
      window.dispatchEvent(new CustomEvent('sdd:sync-syncing', { detail: { syncing: false } }));
    }
  }, [isSyncing]);



  const handleChatKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage]);

  // ══════════════════════════════════════════════════════════════════
  // Render — Landing Page
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

              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2 mt-4">
                📁 Output Directory <span className="text-muted-foreground/60 normal-case font-normal">(optional)</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="w-full px-3 py-2 bg-background border border-border rounded-md font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                  value={outputDir}
                  onChange={handleOutputDirChange}
                  placeholder="C:\\Users\\User\\Documents\\MyProject"
                  id="sdd-output-dir-input"
                />
                <button
                  type="button"
                  onClick={handleCheckRestore}
                  disabled={!outputDir.trim() || restoreStatus === 'checking'}
                  className="px-3 py-2 bg-muted hover:bg-muted/80 text-foreground border border-border rounded-md text-sm font-medium whitespace-nowrap disabled:opacity-50 transition-colors"
                  title="Comprobar si existen archivos .md del proyecto en este directorio"
                >
                  {restoreStatus === 'checking' ? '⏳' : '🔍'}
                </button>
              </div>
              <div className="text-xs mt-1.5 flex flex-col gap-1 text-muted-foreground">
                <span>
                  {outputDir.trim()
                    ? '📂 Files will be saved to this directory'
                    : '💡 Leave empty to keep files in memory only'}
                </span>
                
                {restoreStatus === 'not_found' && (
                  <span className="text-amber-500 font-medium">⚠️ No se encontró ningún proyecto previo. Debes ingresar una idea abajo para empezar.</span>
                )}
                {restoreStatus === 'found' && (
                  <span className="text-emerald-500 font-medium">✅ Proyecto previo detectado. Puedes restaurarlo sin ingresar idea.</span>
                )}
              </div>
            </div>

            <div className="w-full">
              <textarea
                className="w-full min-h-[100px] p-2 bg-card border border-border rounded-md text-xs resize-y focus:outline-none focus:ring-1 focus:ring-primary/50 mb-2 shadow-sm"
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                placeholder={'Describe your software idea...\n\nExample: "I want to build an e-commerce platform with user accounts, product catalog, shopping cart..."'}
                id="sdd-idea-input"
                disabled={!apiKeyValid}
              />
              <button
                className="w-full py-2 bg-gradient-to-r from-primary to-purple-600 hover:from-primary/90 hover:to-purple-600/90 text-white text-xs font-semibold rounded-md shadow-sm disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                onClick={handleStartPipeline}
                disabled={!apiKeyValid || (!idea.trim() && restoreStatus !== 'found')}
                id="sdd-start-pipeline"
              >
                🚀 Generate Spec &amp; Design
              </button>
              
              {restoreStatus === 'found' && (
                <button
                  className="w-full mt-2 py-2 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-500/90 hover:to-teal-600/90 text-white text-xs font-semibold rounded-md shadow-sm disabled:opacity-50 transition-all border border-emerald-400"
                  onClick={handleStartPipeline}
                  disabled={!apiKeyValid}
                  id="sdd-restore-pipeline"
                  title="Restaurar el proyecto detectado en el directorio"
                >
                  📂 Restaurar Proyecto
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════
  // Render — Pipeline Active
  // ══════════════════════════════════════════════════════════════════

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
        </div>
        <div className="flex items-center gap-1.5">
          <button
            className="px-2 py-1 bg-card hover:bg-accent border border-border rounded text-xs font-medium transition-colors"
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
                  phase.status === 'running'
                    ? 'bg-primary/10 border-primary/30 text-primary animate-pulse'
                    : phase.status === 'ready'
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                    : phase.status === 'completed'
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
                    : phase.status === 'error'
                    ? 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400'
                    : 'bg-card border-border text-muted-foreground'
                }`}
              >
                <span>
                  {phase.status === 'completed' ? '✓' :
                   phase.status === 'running' ? '⟳' :
                   phase.status === 'ready' ? '💬' :
                   phase.status === 'error' ? '✕' : phase.icon}
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
                className={`w-full flex items-center justify-between gap-1.5 px-2 py-1.5 rounded-sm text-xs transition-colors text-left ${
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

        {/* Chat — ALWAYS active (agent decides intent) */}
        <div className="flex flex-col flex-1 min-h-0 bg-background relative">
          <div className="p-2 border-b border-border bg-muted/20 text-xs font-semibold text-foreground flex items-center justify-between">
            <span>💬 {pipelineComplete ? 'Vibe Modeling' : 'Pipeline Chat'}</span>
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
                className={`p-2 rounded text-xs max-w-[95%] break-words ${
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

          {/* Chat input — ALWAYS visible once pipeline starts */}
          <div className="p-3 border-t border-border bg-card shrink-0">
            <div className="flex items-end gap-1.5 bg-background border border-border rounded-sm focus-within:ring-1 focus-within:ring-primary/50 overflow-hidden pr-1">
              <textarea
                ref={chatInputRef}
                className="w-full max-h-32 min-h-[32px] bg-transparent text-xs p-1.5 resize-none focus:outline-none"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleChatKeyDown}
                placeholder={pipelineComplete
                  ? 'Modify diagram or requirements... (e.g. "Add email to User")'
                  : 'Type "ok" to continue, or describe changes...'}
                rows={2}
                disabled={isSending}
              />
              <button
                className="mb-1.5 mr-1 p-1.5 text-primary hover:bg-primary/10 rounded-md transition-colors disabled:opacity-50"
                onClick={handleSendMessage}
                disabled={!chatInput.trim() || isSending}
              >
                {isSending ? '⟳' : '➤'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Floating Canvas Overlay for Markdown Viewing */}
      {activeFile && (
        <div className="fixed top-[48px] bottom-0 left-[380px] right-0 z-20 bg-background border-l border-border shadow-xl flex flex-col pointer-events-auto animate-in slide-in-from-right-4 duration-300 xl:left-[450px]">
          <div className="flex items-center px-4 bg-muted/10 border-b border-border shrink-0 min-h-[40px]">
            <div className="flex items-center bg-card border border-border border-b-0 mt-2 px-2.5 py-1 rounded-t text-xs font-medium text-primary">
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
              <div className="mb-6 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-center gap-3">
                <span className="text-2xl">✅</span>
                <div>
                  <h3 className="text-emerald-600 dark:text-emerald-400 font-semibold">Class Diagram Rendered on Canvas</h3>
                  <p className="text-sm text-foreground/80">
                    {canvasJson?.classes?.length || 0} classes, {canvasJson?.relationships?.length || 0} relationships — close this viewer to see them.
                  </p>
                </div>
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
