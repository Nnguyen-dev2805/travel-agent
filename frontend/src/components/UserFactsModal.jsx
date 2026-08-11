import React, { useEffect, useState } from 'react';
import { getUserFacts, deleteUserFact } from '../services/api';

export default function UserFactsModal({ isOpen, onClose }) {
  const [facts, setFacts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchFacts();
    }
  }, [isOpen]);

  const fetchFacts = async () => {
    setIsLoading(true);
    const data = await getUserFacts();
    setFacts(data);
    setIsLoading(false);
  };

  const handleDelete = async (factId) => {
    const success = await deleteUserFact(factId);
    if (success) {
      setFacts((prev) => prev.filter((f) => f.id !== factId));
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg bg-[#1e1e1e] border border-[#383838] rounded-2xl p-6 shadow-2xl text-white overflow-hidden max-h-[85vh] flex flex-col">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-[#2f2f2f] transition-colors"
        >
          <span className="material-symbols-outlined text-xl">close</span>
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 text-purple-400 flex items-center justify-center border border-purple-500/30">
            <span className="material-symbols-outlined text-xl">psychology</span>
          </div>
          <div>
            <h2 className="text-lg font-bold text-white leading-tight">Hồ sơ Ký ức Dài hạn (Long-term Memory)</h2>
            <p className="text-xs text-gray-400">Các sự thật & sở thích AI tự động trích xuất để phục vụ bạn tốt hơn.</p>
          </div>
        </div>

        {/* Facts List Container */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-2.5 custom-scrollbar my-2">
          {isLoading ? (
            <div className="py-8 text-center text-gray-400 text-xs flex items-center justify-center gap-2">
              <span className="material-symbols-outlined text-base animate-spin text-purple-400">sync</span>
              <span>Đang tải danh sách ký ức...</span>
            </div>
          ) : facts.length === 0 ? (
            <div className="py-8 text-center border border-dashed border-[#333] rounded-xl p-4">
              <span className="material-symbols-outlined text-3xl text-gray-500 mb-2">subtitles_off</span>
              <p className="text-xs text-gray-400">Chưa có ký ức cá nhân nào được lưu.</p>
              <p className="text-[11px] text-gray-500 mt-1">Trò chuyện với AI (chia sẻ sở thích, món ăn...) để AI tự động trích xuất!</p>
            </div>
          ) : (
            facts.map((fact) => (
              <div
                key={fact.id}
                className="bg-[#141414] border border-[#2e2e2e] hover:border-purple-500/40 p-3.5 rounded-xl flex items-center justify-between transition-all group"
              >
                <div className="flex items-start gap-3">
                  <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-semibold uppercase tracking-wide border border-purple-500/30 mt-0.5">
                    {fact.fact_type}
                  </span>
                  <div>
                    <p className="text-sm text-gray-200 font-medium">{fact.fact_value}</p>
                    <p className="text-[11px] text-gray-500 font-mono mt-0.5">Key: {fact.fact_key}</p>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(fact.id)}
                  title="Xóa ký ức này"
                  className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-80 group-hover:opacity-100"
                >
                  <span className="material-symbols-outlined text-lg">delete</span>
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer info */}
        <div className="pt-3 border-t border-[#2e2e2e] mt-2 flex justify-between items-center text-[11px] text-gray-400">
          <span>Tổng số ký ức: {facts.length}</span>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#333] text-white rounded-xl text-xs font-semibold transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
