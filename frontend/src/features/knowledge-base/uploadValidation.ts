import { formatBytes } from '@/utils/format';

export const DEFAULT_ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.csv'];
export const DEFAULT_MAX_UPLOAD_MB = 10;
const BYTES_PER_MB = 1024 * 1024;

export function fileExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot).toLowerCase();
}

function normaliseExtensions(extensions: string[] | undefined): string[] {
  const list = extensions && extensions.length > 0 ? extensions : DEFAULT_ALLOWED_EXTENSIONS;
  return list.map((e) => (e.startsWith('.') ? e : `.${e}`).toLowerCase());
}

/** Returns a user-facing error message, or null when the file may be uploaded. */
export function validateUpload(
  file: File,
  maxUploadMb: number = DEFAULT_MAX_UPLOAD_MB,
  allowedExtensions?: string[],
): string | null {
  const allowed = normaliseExtensions(allowedExtensions);
  const ext = fileExtension(file.name);
  if (!allowed.includes(ext)) {
    return `“${file.name}” is not a supported file type. Allowed: ${allowed.join(' ')}`;
  }
  if (file.size === 0) return `“${file.name}” is empty.`;
  const maxBytes = maxUploadMb * BYTES_PER_MB;
  if (file.size > maxBytes) {
    return `“${file.name}” is ${formatBytes(file.size)}, which exceeds the ${maxUploadMb} MB limit.`;
  }
  return null;
}

export function acceptAttribute(allowedExtensions?: string[]): string {
  return normaliseExtensions(allowedExtensions).join(',');
}
