import React, { useState } from 'react';
import { Compass, X, Sparkles, MapPin, Tag } from 'lucide-react';

export default function CreateTripModal({ isOpen, onClose, onCreateTrip }) {
  const [title, setTitle] = useState('');
  const [destination, setDestination] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim() || isSubmitting) return;

    try {
      setIsSubmitting(true);
      await onCreateTrip({
        title: title.trim(),
        destination_scope: destination.trim(),
      });
      setTitle('');
      setDestination('');
      onClose();
    } catch (err) {
      console.error('Lỗi khi tạo chuyến đi:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md bg-surface-card rounded-2xl border border-surface-border shadow-2xl overflow-hidden animate-scale-in">
        {/* Modal Header */}
        <div className="bg-gradient-to-r from-terracotta to-amber p-5 text-white flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white/20 backdrop-blur-md flex items-center justify-center shadow-inner">
              <Compass className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-lg text-white">
                Tạo Chuyến Đi Mới
              </h3>
              <p className="text-xs text-white/90">
                Khởi tạo không gian lên lịch trình thông minh cùng AI
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-700 mb-1.5 flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5 text-terracotta" />
              <span>Tên chuyến đi *</span>
            </label>
            <input
              type="text"
              required
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ví dụ: Du xuân Tây Bắc cùng gia đình"
              className="w-full px-3.5 py-2.5 rounded-xl border border-surface-border bg-white text-sm focus:outline-none focus:ring-2 focus:ring-terracotta/40 focus:border-terracotta text-stone-800 placeholder-stone-400 shadow-xs"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-700 mb-1.5 flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-teal" />
              <span>Điểm đến / Phạm vi (tùy chọn)</span>
            </label>
            <input
              type="text"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Ví dụ: Hà Giang, Đồng Văn, Mèo Vạc"
              className="w-full px-3.5 py-2.5 rounded-xl border border-surface-border bg-white text-sm focus:outline-none focus:ring-2 focus:ring-terracotta/40 focus:border-terracotta text-stone-800 placeholder-stone-400 shadow-xs"
            />
          </div>

          <div className="pt-3 flex items-center justify-end gap-2.5 border-t border-surface-border/60">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2.5 rounded-xl text-stone-600 hover:bg-surface-muted text-sm font-medium transition-colors"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={!title.trim() || isSubmitting}
              className="px-5 py-2.5 rounded-xl bg-terracotta hover:bg-terracotta-hover disabled:opacity-50 text-white text-sm font-semibold shadow-sm hover:shadow transition-all flex items-center gap-1.5"
            >
              <Sparkles className="w-4 h-4" />
              <span>{isSubmitting ? 'Đang tạo...' : 'Tạo chuyến đi'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
