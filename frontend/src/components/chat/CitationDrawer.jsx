import React from 'react';
import { X, ExternalLink, BookOpen, CheckCircle2 } from 'lucide-react';

export default function CitationDrawer({ citation, isOpen, onClose }) {
  if (!isOpen || !citation) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden font-sans">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-deep-charcoal backdrop-blur-xs transition-opacity"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-pure-white border-l border-hairline flex flex-col transform transition-transform animate-slide-left">
          {/* Drawer Header */}
          <div className="h-[52px] px-5 border-b border-hairline flex items-center justify-between bg-sidebar-mist">
            <div className="flex items-center gap-2 text-graphite-ink font-semibold text-caption">
              <BookOpen className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
              <span>Nguồn Dữ Liệu Du Lịch (RAG Citation)</span>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Đóng bảng trích dẫn"
              className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
            >
              <X className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* Title & Badge */}
            <div className="space-y-2">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-hairline bg-sidebar-mist text-[12px] font-medium text-graphite-ink">
                <CheckCircle2 className="w-3.5 h-3.5 text-graphite-ink" aria-hidden="true" />
                <span>Nguồn Trích Dẫn Đã Xác Thực</span>
              </span>
              <h2 className="text-[17px] font-semibold text-graphite-ink leading-snug">
                {citation.title || 'Tài liệu du lịch Việt Nam'}
              </h2>
            </div>

            {/* URL Source */}
            {citation.url && (
              <div className="p-3.5 rounded-lg bg-sidebar-mist border border-hairline space-y-1">
                <div className="text-[11px] font-medium text-mid-ash uppercase tracking-wider">
                  Liên kết bài viết chính thức
                </div>
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-caption text-graphite-ink underline hover:text-black flex items-center gap-1 break-all"
                >
                  <ExternalLink className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                  <span>{citation.url}</span>
                </a>
              </div>
            )}

            {/* Evidence details */}
            <div className="space-y-2">
              <div className="text-[11px] font-medium text-mid-ash uppercase tracking-wider">
                Đoạn trích cẩm nang được mô hình tham khảo
              </div>
              <div className="p-3.5 rounded-lg bg-sidebar-mist/60 border border-hairline text-caption text-graphite-ink leading-relaxed whitespace-pre-wrap">
                {citation.snippet ||
                  'Nội dung cẩm nang này đã được hệ thống tìm kiếm vector trong cơ sở dữ liệu ChromaDB và tổng hợp vào ngữ cảnh sinh câu trả lời của Trợ lý AI.'}
              </div>
            </div>

            {/* Chunk provenance IDs */}
            {citation.evidence_ids && citation.evidence_ids.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[11px] font-medium text-hollow uppercase tracking-wider">
                  Mã đoạn trích (Chunk IDs)
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {citation.evidence_ids.map((id, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded text-[11px] font-mono bg-sidebar-mist text-mid-ash border border-hairline"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-3.5 border-t border-hairline bg-sidebar-mist text-center">
            <p className="text-[11px] text-hollow">
              Dữ liệu được làm sạch từ Cục Du lịch Quốc gia Việt Nam (vietnam.travel)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
