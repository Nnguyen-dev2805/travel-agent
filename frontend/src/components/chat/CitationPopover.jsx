import React, { useState, useRef, useEffect } from 'react';
import { ExternalLink, X, BookOpen } from 'lucide-react';

export default function CitationPopover({ citation, index }) {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef(null);

  // Close when clicking outside or pressing Escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (popoverRef.current && !popoverRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  if (!citation) return null;

  return (
    <span className="relative inline-block font-sans" ref={popoverRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label={`Xem nguồn tài liệu: ${citation.title || 'Cẩm nang du lịch'}`}
        aria-expanded={isOpen}
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-caption font-medium bg-sidebar-mist hover:bg-hover-veil text-graphite-ink border border-hairline transition-colors cursor-pointer select-none focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
        title="Xem nguồn tài liệu"
      >
        <span className="font-semibold text-graphite-ink">[{index + 1}]</span>
        <span className="truncate max-w-[130px] sm:max-w-[180px]">
          {citation.title || 'Cẩm nang du lịch'}
        </span>
      </button>

      {/* Surface Level 2: Elevated Panel (Pure White #ffffff, 10px radius, 1px hairline border, no shadow) */}
      {isOpen && (
        <div
          role="dialog"
          aria-label="Chi tiết nguồn trích dẫn"
          className="absolute z-50 bottom-full mb-2 left-0 sm:left-auto sm:-translate-x-1/4 w-72 sm:w-80 p-3.5 bg-pure-white rounded-lg border border-hairline text-graphite-ink text-caption animate-fade-in space-y-2.5"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-hairline pb-2">
            <div className="flex items-center gap-1.5 text-[12px] font-medium text-mid-ash">
              <BookOpen className="w-3.5 h-3.5 text-mid-ash" aria-hidden="true" />
              <span>Nguồn xác thực</span>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Đóng bảng nguồn trích dẫn"
              className="p-1 rounded text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
            >
              <X className="w-3.5 h-3.5" aria-hidden="true" />
            </button>
          </div>

          {/* Title */}
          <h3 className="font-semibold text-graphite-ink text-caption leading-snug line-clamp-2 text-pretty">
            {citation.title || 'Tài liệu du lịch Việt Nam'}
          </h3>

          {/* Snippet text */}
          {citation.snippet && (
            <p className="text-[13px] text-mid-ash leading-relaxed bg-sidebar-mist p-2 rounded border border-hairline line-clamp-4 italic">
              &ldquo;{citation.snippet}&rdquo;
            </p>
          )}

          {/* Source Link */}
          {citation.url ? (
            <div className="pt-1">
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[13px] text-graphite-ink font-medium flex items-center gap-1 truncate hover:underline focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none rounded"
              >
                <ExternalLink className="w-3 h-3 shrink-0 text-mid-ash" aria-hidden="true" />
                <span className="truncate">{citation.url}</span>
              </a>
            </div>
          ) : (
            <div className="text-[11px] text-hollow pt-1">
              Cơ sở dữ liệu: Cục Du lịch Quốc gia Việt Nam
            </div>
          )}
        </div>
      )}
    </span>
  );
}
