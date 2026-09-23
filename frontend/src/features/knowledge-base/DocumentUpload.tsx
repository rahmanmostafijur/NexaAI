import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, UploadCloud } from 'lucide-react';
import { useId, useRef, useState, type DragEvent } from 'react';
import { Spinner } from '@/components/ui/Spinner';
import { useToast } from '@/components/ui/toast';
import { useSystemInfo } from '@/hooks/useSystemInfo';
import { uploadDocument } from '@/services/documents';
import { errorMessage } from '@/services/http';
import { queryKeys } from '@/services/queryKeys';
import { cn } from '@/utils/cn';
import { formatBytes } from '@/utils/format';
import { DEFAULT_MAX_UPLOAD_MB, acceptAttribute, validateUpload } from './uploadValidation';

interface PendingUpload {
  id: string;
  name: string;
  size: number;
}

export function DocumentUpload() {
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const info = useSystemInfo();
  const maxMb = info.data?.max_upload_mb ?? DEFAULT_MAX_UPLOAD_MB;
  const allowed = info.data?.allowed_extensions;
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [pending, setPending] = useState<PendingUpload[]>([]);

  async function uploadOne(file: File, id: string) {
    try {
      await uploadDocument(file);
      notify({
        tone: 'success',
        title: 'Upload started',
        description: `${file.name} is being indexed.`,
      });
    } catch (err) {
      setErrors((e) => [...e, `${file.name}: ${errorMessage(err)}`]);
    } finally {
      setPending((p) => p.filter((u) => u.id !== id));
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
    }
  }

  function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    const files = Array.from(list);
    const nextErrors: string[] = [];
    const accepted: { file: File; id: string }[] = [];
    files.forEach((file, index) => {
      const problem = validateUpload(file, maxMb, allowed);
      if (problem) nextErrors.push(problem);
      else accepted.push({ file, id: `${Date.now()}-${index}-${file.name}` });
    });
    setErrors(nextErrors);
    setPending((p) => [
      ...p,
      ...accepted.map(({ file, id }) => ({ id, name: file.name, size: file.size })),
    ]);
    accepted.forEach(({ file, id }) => void uploadOne(file, id));
    if (input.current) input.current.value = '';
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  return (
    <div className="space-y-3">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors',
          dragging
            ? 'border-accent bg-accent-soft/50'
            : 'border-line hover:border-line-strong hover:bg-surface-2/60',
        )}
      >
        <UploadCloud className="size-7 text-fg-subtle" aria-hidden />
        <span className="mt-2 text-sm font-medium text-fg">
          Drop files here or <span className="text-accent">browse</span>
        </span>
        <span className="mt-1 text-xs text-fg-subtle">
          PDF, DOCX, TXT, Markdown or CSV · up to {maxMb} MB each
        </span>
        <input
          ref={input}
          id={inputId}
          type="file"
          multiple
          accept={acceptAttribute(allowed)}
          className="sr-only"
          aria-label="Upload documents"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </label>

      {errors.length > 0 && (
        <ul role="alert" className="space-y-1 rounded-lg bg-danger-soft px-3 py-2">
          {errors.map((message) => (
            <li key={message} className="flex items-start gap-2 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden /> {message}
            </li>
          ))}
        </ul>
      )}

      {pending.length > 0 && (
        <ul aria-label="Uploads in progress" className="space-y-1">
          {pending.map((u) => (
            <li
              key={u.id}
              className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
            >
              <Spinner size="sm" className="text-accent" />
              <span className="min-w-0 flex-1 truncate text-fg">{u.name}</span>
              <span className="text-xs text-fg-subtle">{formatBytes(u.size)} · uploading</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
