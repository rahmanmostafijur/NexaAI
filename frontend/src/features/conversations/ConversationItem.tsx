import { Check, Pencil, Trash2, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { NavLink } from 'react-router-dom';
import { IconButton } from '@/components/ui/IconButton';
import type { ConversationSummary } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatRelativeTime } from '@/utils/format';
import { langFor } from '@/utils/script';

const MAX_TITLE = 200;

export function ConversationItem({
  conversation,
  onRename,
  onDelete,
  onNavigate,
}: {
  conversation: ConversationSummary;
  onRename: (id: string, title: string) => Promise<void>;
  onDelete: (conversation: ConversationSummary) => void;
  onNavigate?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const title = draft.trim();
    if (!title || title === conversation.title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onRename(conversation.id, title);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <li>
        <form
          onSubmit={submit}
          className="flex items-center gap-1 rounded-lg bg-surface-2 px-1.5 py-1"
        >
          <input
            autoFocus
            value={draft}
            maxLength={MAX_TITLE}
            aria-label="Conversation title"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setEditing(false);
            }}
            className="h-7 min-w-0 flex-1 rounded-md border border-line bg-surface px-2 text-sm text-fg focus:border-accent focus:outline-none"
          />
          <IconButton
            type="submit"
            size="sm"
            label="Save title"
            disabled={saving}
            icon={<Check className="size-3.5" />}
          />
          <IconButton
            size="sm"
            label="Cancel rename"
            onClick={() => setEditing(false)}
            icon={<X className="size-3.5" />}
          />
        </form>
      </li>
    );
  }

  return (
    <li className="group/item relative">
      <NavLink
        to={`/c/${conversation.id}`}
        onClick={onNavigate}
        className={({ isActive }) =>
          cn(
            'block rounded-lg py-2 pr-16 pl-3 text-sm transition-colors',
            isActive ? 'bg-surface-3 text-fg' : 'text-fg-muted hover:bg-surface-2 hover:text-fg',
          )
        }
      >
        <span className="block truncate" lang={langFor(conversation.title)}>
          {conversation.title || 'Untitled chat'}
        </span>
        <span className="block text-[11px] text-fg-subtle">
          {formatRelativeTime(conversation.updated_at)}
        </span>
      </NavLink>
      <div className="absolute top-1/2 right-1.5 flex -translate-y-1/2 gap-0.5 opacity-0 transition-opacity group-focus-within/item:opacity-100 group-hover/item:opacity-100">
        <IconButton
          size="sm"
          label={`Rename ${conversation.title}`}
          icon={<Pencil className="size-3.5" />}
          onClick={() => {
            setDraft(conversation.title);
            setEditing(true);
          }}
        />
        <IconButton
          size="sm"
          label={`Delete ${conversation.title}`}
          icon={<Trash2 className="size-3.5" />}
          onClick={() => onDelete(conversation)}
        />
      </div>
    </li>
  );
}
