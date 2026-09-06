import React from 'react';
import { X, ExternalLink, BookOpen, CheckCircle2 } from 'lucide-react';

export default function CitationDrawer({ citation, isOpen, onClose }) {
  if (!isOpen || !citation) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="absolute inset-0 bg-stone-900/30 backdrop-blur-xs transition-opacity"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-surface-card border-l border-surface-border shadow-2xl flex flex-col transform transition-transform animate-slide-left">
          {/* Drawer Header */}
          <div className="h-16 px-6 border-b border-surface-border flex items-center justify-between bg-surface-muted/60">
            <div className="flex items-center gap-2.5 text-stone-800 font-bold text-sm">
              <BookOpen className="w-4 h-4 text-terracotta" />
              <span>Nguồn Dữ Liệu Du Lịch (RAG Citation)</span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-200/60 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Title & Badge */}
            <div className="space-y-2">
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-terracotta/10 text-terracotta border border-terracotta/20">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Nguồn Trích Dẫn Đã Xác Thực</span>
              </span>
              <h2 className="text-xl font-bold text-stone-900 leading-snug">
                {citation.title || 'Tài liệu du lịch Việt Nam'}
              </h2>
            </div>

            {/* URL Source */}
            {citation.url && (
              <div className="p-3.5 rounded-xl bg-surface-muted border border-surface-border space-y-1.5">
                <div className="text-xs font-semibold text-stone-500 uppercase tracking-wider">
                  Liên kết bài viết chính thức
                </div>
                <a
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-teal hover:underline flex items-center gap-1 font-medium break-all"
                >
                  <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                  <span>{citation.url}</span>
                </a>
              </div>
            )}

            {/* Evidence details */}
            <div className="space-y-3">
              <div className="text-xs font-semibold text-stone-500 uppercase tracking-wider">
                Đoạn trích cẩm nang được mô hình tham khảo
              </div>
              <div className="p-4 rounded-xl bg-surface-muted/50 border border-surface-border text-xs text-stone-700 leading-relaxed font-serif whitespace-pre-wrap">
                {citation.snippet ||
                  'Nội dung cẩm nang này đã được hệ thống tìm kiếm vector trong cơ sở dữ liệu ChromaDB và tổng hợp vào ngữ cảnh sinh câu trả lời của Trợ lý AI.'}
              </div>
            </div>

            {/* Chunk provenance IDs */}
            {citation.evidence_ids && citation.evidence_ids.length > 0 && (
              <div className="space-y-2">
                <div className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider">
                  Mã đoạn trích (Chunk IDs)
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {citation.evidence_ids.map((id, idx) => (
                    <span
                      key={idx}
                      className="px-2 py-0.5 rounded text-[11px] font-mono bg-stone-100 text-stone-600 border border-stone-200"
                    >
                      {id}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-4 border-t border-surface-border bg-surface-muted/40 text-center">
            <p className="text-[11px] text-stone-400">
              Dữ liệu được làm sạch từ Cục Du lịch Quốc gia Việt Nam (vietnam.travel)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
