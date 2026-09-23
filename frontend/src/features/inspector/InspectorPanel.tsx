import { Microscope, X } from 'lucide-react';
import { EmptyState } from '@/components/ui/EmptyState';
import { IconButton } from '@/components/ui/IconButton';
import { Drawer } from '@/components/ui/Overlay';
import type { ChatMessage } from '@/features/chat/types';
import { LARGE_SCREEN_QUERY, useMediaQuery } from '@/hooks/useMediaQuery';
import { inspectorDataFor } from './inspectorData';
import {
  AnalysisSection,
  PlanSection,
  SourcesSection,
  SqlSection,
  TimingsSection,
  ToolsSection,
} from './InspectorSections';

function InspectorBody({ message }: { message: ChatMessage | null }) {
  if (!message) {
    return (
      <EmptyState
        icon={<Microscope className="size-5" aria-hidden />}
        title="Nothing to inspect yet"
        description="Ask a question to see how the agent analyzed, routed, and answered it."
      />
    );
  }
  const data = inspectorDataFor(message);
  return (
    <div>
      <AnalysisSection data={data} />
      <PlanSection data={data} />
      <ToolsSection data={data} />
      <SourcesSection data={data} />
      <SqlSection data={data} />
      <TimingsSection data={data} />
    </div>
  );
}

/** Right-hand execution inspector: docked panel on large screens, slide-over drawer otherwise. */
export function InspectorPanel({
  message,
  open,
  onClose,
}: {
  message: ChatMessage | null;
  open: boolean;
  onClose: () => void;
}) {
  const isLarge = useMediaQuery(LARGE_SCREEN_QUERY);

  if (!isLarge) {
    return (
      <Drawer open={open} onClose={onClose} title="Inspector">
        <div className="-mx-5 -my-4">
          <InspectorBody message={message} />
        </div>
      </Drawer>
    );
  }
  if (!open) return null;
  return (
    <aside
      aria-label="Inspector"
      className="flex w-[360px] shrink-0 flex-col border-l border-line bg-surface xl:w-[400px]"
    >
      <div className="flex h-14 items-center justify-between border-b border-line px-4">
        <h2 className="text-sm font-semibold text-fg">Inspector</h2>
        <IconButton
          label="Close inspector"
          size="sm"
          icon={<X className="size-4" />}
          onClick={onClose}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <InspectorBody message={message} />
      </div>
    </aside>
  );
}
