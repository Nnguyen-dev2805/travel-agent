import React from 'react';

export default function MemoryConfirmation({
  preview,
  onConfirm,
  onCancel,
  confirming,
  error,
}) {
  if (!preview) return null;
  const isExpansion = preview.operation === 'scope_expansion';
  const targets = preview.targets || [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-confirm-title"
      className="rounded-lg border border-hairline bg-white p-4"
    >
      <h3 id="memory-confirm-title" className="text-base font-semibold">
        {isExpansion ? 'Widen memory scope?' : 'Review this delete'}
      </h3>
      <p className="mt-1 text-sm text-gray-600">
        {isExpansion
          ? 'This widens one conversation memory to user scope across every chat.'
          : 'This removes the listed memories.'}
      </p>
      <ul className="mt-2 space-y-1 text-sm">
        {targets.map((target) => (
          <li key={target.version_id}>
            <span className="font-medium">{target.normalized_value}</span>
            {' · '}
            <span>{target.canonical_key}</span>
            {' · '}
            {isExpansion ? (
              <span>
                {target.old_scope || target.scope} &rarr; {target.new_scope || 'user'}
              </span>
            ) : (
              <span>{target.scope}</span>
            )}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-gray-500">
        Expires in {Math.round(preview.expires_in_seconds || 0)} seconds.
      </p>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={confirming}
          autoFocus
          className="rounded bg-graphite-ink px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {confirming ? 'Working…' : 'Confirm'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={confirming}
          className="rounded border border-hairline px-3 py-1 text-sm"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
