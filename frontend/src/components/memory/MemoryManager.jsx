import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  listMemories,
  sendMemoryCommand,
  createDeletion,
  requestScopeExpansion,
  confirmPreview,
} from '../../services/memory';
import MemoryConfirmation from './MemoryConfirmation';

const noticeFor = (response) => {
  switch (response?.status) {
    case 'saved':
      return `Saved ${response.normalized_value} memory.`;
    case 'deleted':
      return 'Deleted memory.';
    case 'committed':
      return `Deleted ${response.committed_version_ids?.length || 0} memories.`;
    case 'toggled':
      return response.persistent
        ? 'Memory toggled.'
        : 'Memory toggled for this session (not stored).';
    case 'held':
    case 'refused':
      return `Not saved: ${response.reason_code || 'refused'}.`;
    case 'pending':
      return `Pending: ${response.reason_code || 'needs review'}.`;
    default:
      return 'Done.';
  }
};

export default function MemoryManager({ onClose }) {
  const [status, setStatus] = useState('loading');
  const [memories, setMemories] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [utterance, setUtterance] = useState('');
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState('');
  const headingRef = useRef(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setLoadError('');
    try {
      const items = await listMemories();
      setMemories(items || []);
      setStatus('ready');
    } catch (err) {
      setStatus('error');
      setLoadError(err?.message || 'Could not load memories.');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (preview) {
          setPreview(null);
          setConfirmError('');
        } else {
          onClose?.();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, preview]);

  const refreshAfterWrite = async (response) => {
    setNotice(noticeFor(response));
    try {
      setMemories((await listMemories()) || []);
    } catch {
      // List refresh is best-effort after a confirmed write.
    }
  };

  const handleSend = async (e) => {
    e?.preventDefault?.();
    const text = utterance.trim();
    if (!text || sending) return;
    setSending(true);
    setNotice('');
    try {
      const response = await sendMemoryCommand({ utterance: text });
      if (response?.status === 'preview_required' && response?.preview) {
        setPreview(response.preview);
        setConfirmError('');
      } else {
        await refreshAfterWrite(response);
      }
      setUtterance('');
    } catch (err) {
      setNotice(err?.message || 'Command failed.');
    } finally {
      setSending(false);
    }
  };

  const handleDeleteOne = async (versionId) => {
    setNotice('');
    try {
      const response = await createDeletion({ version_ids: [versionId] });
      if (response?.status === 'preview_required' && response?.preview) {
        setPreview(response.preview);
        setConfirmError('');
      } else {
        await refreshAfterWrite(response);
      }
    } catch (err) {
      setNotice(err?.message || 'Delete failed.');
    }
  };

  const handleExpand = async (versionId) => {
    setNotice('');
    setConfirmError('');
    try {
      const response = await requestScopeExpansion({ version_id: versionId });
      if (response?.status === 'preview_required' && response?.preview) {
        setPreview(response.preview);
      } else {
        await refreshAfterWrite(response);
      }
    } catch (err) {
      setNotice(err?.message || 'Expansion failed.');
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(true);
    setConfirmError('');
    try {
      const response = await confirmPreview({
        preview_id: preview.preview_id,
        token: preview.token,
      });
      setPreview(null);
      await refreshAfterWrite(response);
    } catch (err) {
      setConfirmError(err?.message || 'Confirmation failed.');
    } finally {
      setConfirming(false);
    }
  };

  return (
    <section aria-label="Memory manager" className="flex h-full flex-col gap-3 p-4">
      <h2
        ref={headingRef}
        data-testid="memory-manager-heading"
        tabIndex={-1}
        className="text-lg font-semibold outline-none"
      >
        Memory manager
      </h2>

      <div aria-live="polite" className="min-h-[1.5rem] text-sm">
        {notice}
      </div>

      <form onSubmit={handleSend} className="flex gap-2">
        <label htmlFor="memory-command-input" className="sr-only">
          Memory command
        </label>
        <input
          id="memory-command-input"
          type="text"
          value={utterance}
          onChange={(e) => setUtterance(e.target.value)}
          placeholder="remember quiet hotels"
          className="flex-1 rounded border border-hairline px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={sending || !utterance.trim()}
          className="rounded bg-graphite-ink px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          Save
        </button>
        <button
          type="button"
          onClick={load}
          className="rounded border border-hairline px-3 py-1 text-sm"
        >
          Refresh
        </button>
      </form>

      {preview && (
        <MemoryConfirmation
          preview={preview}
          onConfirm={handleConfirm}
          onCancel={() => {
            setPreview(null);
            setConfirmError('');
          }}
          confirming={confirming}
          error={confirmError}
        />
      )}

      {status === 'loading' && <p className="text-sm">Loading memories…</p>}
      {status === 'error' && (
        <div className="text-sm">
          <p>Could not load memories: {loadError}</p>
          <button
            type="button"
            onClick={load}
            className="mt-1 rounded border border-hairline px-3 py-1 text-sm"
          >
            Retry
          </button>
        </div>
      )}
      {status === 'ready' && memories.length === 0 && (
        <p className="text-sm">No saved memories yet.</p>
      )}
      {status === 'ready' && memories.length > 0 && (
        <ul className="space-y-2 overflow-y-auto text-sm">
          {memories.map((item) => (
            <li
              key={item.version_id}
              className="flex items-center justify-between gap-2 rounded border border-hairline p-2"
            >
              <div>
                <span className="font-medium">{item.normalized_value}</span>
                {' · '}
                <span className="text-gray-600">{item.canonical_key}</span>
                {' · '}
                <span className="text-gray-600">{item.scope}</span>
              </div>
              <div className="flex shrink-0 gap-1">
                {item.scope === 'conversation' && (
                  <button
                    type="button"
                    onClick={() => handleExpand(item.version_id)}
                    className="rounded border border-hairline px-2 py-0.5 text-xs"
                  >
                    Expand
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => handleDeleteOne(item.version_id)}
                  className="rounded border border-hairline px-2 py-0.5 text-xs"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
