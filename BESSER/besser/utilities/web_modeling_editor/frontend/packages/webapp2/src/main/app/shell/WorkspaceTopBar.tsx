import React from 'react';
import { FolderKanban } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { CommunityMenu } from './menus/CommunityMenu';
import { DeployMenu } from './menus/DeployMenu';
import { FileMenu } from './menus/FileMenu';
import { GenerateMenu } from './menus/GenerateMenu';
import { HelpMenu } from './menus/HelpMenu';
import { MobileNavigation } from './menus/MobileNavigation';
import { TopBarUtilities } from './menus/TopBarUtilities';
import type { WorkspaceTopBarProps } from './topbar-types';

const WorkspaceTopBarInner: React.FC<WorkspaceTopBarProps> = ({
  isDarkTheme,
  headerBackgroundClass,
  outlineButtonClass,
  primaryGenerateClass,
  showQualityCheck,
  generatorMode,
  isGenerating,
  locationPath,
  activeUmlType,
  isAuthenticated,
  username,
  githubLoading,
  hasProject,
  isDeploymentAvailable,
  onOpenProjectHub,
  onOpenTemplateDialog,
  onExportProject,
  onImportSingleDiagram,
  onOpenAssistantImportImage,
  onOpenAssistantImportKg,
  onOpenProjectPreview,
  onGenerate,
  onQualityCheck,
  onToggleTheme,
  onGitHubLogin,
  onGitHubLogout,
  onOpenGitHubSidebar,
  hasStarred,
  starLoading,
  onToggleStar,
  onOpenDeployDialog,
  onOpenHelpDialog,
  onOpenAboutDialog,
  onOpenFeedback,
  onOpenKeyboardShortcuts,
  onShowWelcomeGuide,
  activeDiagramType,
  onSwitchUml,
  onSwitchDiagramType,
  onNavigate,
  projectNameDraft,
  onProjectNameDraftChange,
  onProjectRename,
  onOpenCCSDD,
  sddSyncAvailable,
  sddSyncSyncing,
  onSddSyncTrigger,
}) => {
  return (
    <header className={`relative z-20 animate-slide-in-down px-4 py-2 sm:px-6 ${headerBackgroundClass}`}>
      <style>{`
        @keyframes sdd-topbar-pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.4); }
          50% { box-shadow: 0 0 0 4px rgba(99, 102, 241, 0); }
        }
        @keyframes sdd-sync-spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            onClick={onOpenProjectHub}
            aria-label="Open project hub"
            className="group flex shrink-0 items-center p-0 text-left transition-opacity hover:opacity-85"
          >
            <img
              src="/images/logo.png"
              alt="BESSER"
              className={`h-10 w-auto ${isDarkTheme ? 'brightness-0 invert' : 'brightness-0'}`}
            />
          </button>
          <div className="hidden items-center gap-1.5 lg:flex">
            <FolderKanban className="size-4 shrink-0 text-muted-foreground" />
            <Input
              value={projectNameDraft}
              onChange={(event) => onProjectNameDraftChange(event.target.value)}
              onBlur={onProjectRename}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.currentTarget.blur();
                }
              }}
              className="h-7 w-36 border-none bg-transparent px-1 py-0 text-sm font-medium shadow-none focus-visible:ring-0"
              placeholder="Project name"
            />
          </div>
        </div>

        <div className="flex items-center gap-1 xl:gap-2">
          <FileMenu
            outlineButtonClass={outlineButtonClass}
            hasProject={hasProject}
            onOpenProjectHub={onOpenProjectHub}
            onOpenTemplateDialog={onOpenTemplateDialog}
            onExportProject={onExportProject}
            onImportSingleDiagram={onImportSingleDiagram}
            onOpenAssistantImportImage={onOpenAssistantImportImage}
            onOpenAssistantImportKg={onOpenAssistantImportKg}
            onOpenProjectPreview={onOpenProjectPreview}
          />
          <GenerateMenu
            mode={generatorMode}
            isGenerating={isGenerating}
            primaryGenerateClass={primaryGenerateClass}
            onGenerate={onGenerate}
            onSwitchDiagramType={onSwitchDiagramType}
          />
          <DeployMenu
            outlineButtonClass={outlineButtonClass}
            isAuthenticated={isAuthenticated}
            githubLoading={githubLoading}
            isDeploymentAvailable={isDeploymentAvailable}
            onGitHubLogin={onGitHubLogin}
            onOpenDeployDialog={onOpenDeployDialog}
          />
          <CommunityMenu
            outlineButtonClass={outlineButtonClass}
            onOpenFeedback={onOpenFeedback}
          />
          <HelpMenu
            outlineButtonClass={outlineButtonClass}
            onOpenHelpDialog={onOpenHelpDialog}
            onOpenAboutDialog={onOpenAboutDialog}
            onOpenKeyboardShortcuts={onOpenKeyboardShortcuts}
            onShowWelcomeGuide={onShowWelcomeGuide}
          />
          <button
            type="button"
            onClick={onOpenCCSDD}
            title="CC-SDD: Spec-Driven Development Studio"
            className={`hidden lg:inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold transition-colors ${outlineButtonClass}`}
            style={{
              background: isDarkTheme
                ? 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(168,85,247,0.15))'
                : 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(168,85,247,0.08))',
              borderColor: isDarkTheme ? 'rgba(99,102,241,0.4)' : 'rgba(99,102,241,0.25)',
            }}
          >
            <span>⚡</span>
            <span style={{
              background: 'linear-gradient(135deg, #6366f1, #a855f7)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>CC-SDD</span>
          </button>
          {/* ── Sync Button — next to CC-SDD ── */}
          {sddSyncAvailable && (
            <button
              type="button"
              onClick={onSddSyncTrigger}
              disabled={sddSyncSyncing}
              id="sdd-sync-diagram-topbar"
              title="Sincronizar cambios del diagrama con requisitos y trazabilidad"
              className="sdd-sync-button-topbar"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 14px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 700,
                cursor: sddSyncSyncing ? 'wait' : 'pointer',
                border: '2px solid',
                whiteSpace: 'nowrap' as const,
                transition: 'all 0.2s ease',
                background: sddSyncSyncing
                  ? (isDarkTheme ? 'hsl(220 15% 18%)' : 'hsl(220 15% 92%)')
                  : 'linear-gradient(135deg, #6366f1, #a855f7)',
                borderColor: sddSyncSyncing
                  ? (isDarkTheme ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)')
                  : 'rgba(99,102,241,0.5)',
                color: sddSyncSyncing
                  ? (isDarkTheme ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)')
                  : 'white',
                animation: sddSyncSyncing ? 'none' : 'sdd-topbar-pulse 2s ease-in-out infinite',
              }}
            >
              <span style={{
                display: 'inline-flex',
                fontSize: '14px',
                animation: sddSyncSyncing ? 'sdd-sync-spin 1s linear infinite' : 'none',
              }}>
                {sddSyncSyncing ? '⟳' : '🔄'}
              </span>
              <span className="hidden xl:inline">{sddSyncSyncing ? 'Sincronizando...' : 'Sincronizar'}</span>
            </button>
          )}
          <TopBarUtilities
            showQualityCheck={showQualityCheck}
            outlineButtonClass={outlineButtonClass}
            isDarkTheme={isDarkTheme}
            isAuthenticated={isAuthenticated}
            username={username}
            githubLoading={githubLoading}
            hasStarred={hasStarred}
            starLoading={starLoading}
            onQualityCheck={onQualityCheck}
            onToggleTheme={onToggleTheme}
            onGitHubLogin={onGitHubLogin}
            onGitHubLogout={onGitHubLogout}
            onOpenGitHubSidebar={onOpenGitHubSidebar}
            onToggleStar={onToggleStar}
          />
        </div>
      </div>
      <MobileNavigation
        locationPath={locationPath}
        activeUmlType={activeUmlType}
        activeDiagramType={activeDiagramType}
        isDarkTheme={isDarkTheme}
        onSwitchUml={onSwitchUml}
        onSwitchDiagramType={onSwitchDiagramType}
        onNavigate={onNavigate}
      />
    </header>
  );
};

export const WorkspaceTopBar = React.memo(WorkspaceTopBarInner);
