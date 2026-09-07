import React, { useState, useEffect } from 'react';
import { Compass, X, Sparkles, MapPin, Tag } from 'lucide-react';

export default function CreateTripModal({ isOpen, onClose, onCreateTrip }) {
  const [title, setTitle] = useState('');
  const [destination, setDestination] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

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
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-trip-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 font-sans"
    >
      {/* Scrim Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-[#00000080] transition-opacity"
        aria-hidden="true"
      />

      {/* Modal Card: Solid Pure White Surface Level 2 */}
      <div className="relative z-10 w-full max-w-md bg-white rounded-lg border border-hairline overflow-hidden">
        {/* Modal Header */}
        <div className="p-5 border-b border-hairline flex items-center justify-between bg-white">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg border border-hairline bg-sidebar-mist flex items-center justify-center text-graphite-ink">
              <Compass className="w-4 h-4 stroke-[1.8]" aria-hidden="true" />
            </div>
            <div>
              <h3 id="create-trip-title" className="font-semibold text-caption text-graphite-ink">
                Tạo Chuyến Đi Mới
              </h3>
              <p className="text-[12px] text-mid-ash mt-0.5">
                Khởi tạo không gian lên lịch trình thông minh cùng AI
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng cửa sổ tạo chuyến đi"
            className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 bg-white">
          <div>
            <label
              htmlFor="trip-title-input"
              className="text-caption font-medium text-graphite-ink mb-1.5 flex items-center gap-1.5"
            >
              <Tag className="w-3.5 h-3.5 text-mid-ash" aria-hidden="true" />
              <span>Tên chuyến đi *</span>
            </label>
            <input
              id="trip-title-input"
              type="text"
              required
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Ví dụ: Du xuân Tây Bắc cùng gia đình"
              className="w-full px-3 py-2 rounded-lg border border-hairline bg-white text-caption text-graphite-ink placeholder-hollow focus:outline-none focus:ring-1 focus:ring-graphite-ink focus:border-graphite-ink transition-colors"
            />
          </div>

          <div>
            <label
              htmlFor="trip-dest-input"
              className="text-caption font-medium text-graphite-ink mb-1.5 flex items-center gap-1.5"
            >
              <MapPin className="w-3.5 h-3.5 text-mid-ash" aria-hidden="true" />
              <span>Điểm đến / Phạm vi (tùy chọn)</span>
            </label>
            <input
              id="trip-dest-input"
              type="text"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Ví dụ: Hà Giang, Đồng Văn, Mèo Vạc"
              className="w-full px-3 py-2 rounded-lg border border-hairline bg-white text-caption text-graphite-ink placeholder-hollow focus:outline-none focus:ring-1 focus:ring-graphite-ink focus:border-graphite-ink transition-colors"
            />
          </div>

          <div className="pt-3 flex items-center justify-end gap-2 border-t border-hairline">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-2 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil text-caption font-medium transition-colors"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={!title.trim() || isSubmitting}
              className="px-4 py-2 rounded-lg bg-graphite-ink hover:bg-black disabled:opacity-40 text-white text-caption font-medium transition-colors flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
            >
              <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
              <span>{isSubmitting ? 'Đang tạo…' : 'Tạo chuyến đi'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
