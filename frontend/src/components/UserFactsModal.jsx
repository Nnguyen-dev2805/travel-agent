import React, { useEffect, useState } from 'react';
import { getUserFacts, deleteUserFact, updateMemoryConsent } from '../services/api';
import { Brain, X, Trash2, Loader2, FolderX, ToggleLeft, ToggleRight } from 'lucide-react';

export default function UserFactsModal({ isOpen, onClose, currentUser, onConsentChange }) {
  const [facts, setFacts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingConsent, setIsSavingConsent] = useState(false);

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

  const handleToggleConsent = async () => {
    if (!currentUser) return;
    setIsSavingConsent(true);
    const newConsent = !currentUser.memory_enabled;
    const updatedUser = await updateMemoryConsent(newConsent);
    if (updatedUser && onConsentChange) {
      onConsentChange(updatedUser.memory_enabled);
    }
    setIsSavingConsent(false);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#00000080] animate-fade-in">
      <div className="relative w-full max-w-lg bg-[#ffffff] border border-[#0000001a] rounded-[10px] p-6 text-[#0d0d0d] overflow-hidden max-h-[85vh] flex flex-col">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[#5d5d5d] hover:text-[#0d0d0d] p-1.5 rounded-[10px] hover:bg-[#0000000d] transition-colors cursor-pointer"
        >
          <X className="w-5 h-5 stroke-[1.75]" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-[10px] bg-[#f9f9f9] text-[#0d0d0d] flex items-center justify-center border border-[#0000001a]">
            <Brain className="w-5 h-5 text-[#0d0d0d] stroke-[1.75]" />
          </div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-[#0d0d0d] leading-tight">Long-term AI Memory (User Facts)</h2>
            <p className="text-xs text-[#5d5d5d]">Personalized facts & preferences automatically remembered by AI.</p>
          </div>
        </div>

        {/* Consent Toggle Area */}
        {currentUser && (
          <div className="flex items-center justify-between p-3 mb-2 rounded-[10px] border border-[#0000001a] bg-[#f9f9f9]">
            <div>
              <p className="text-sm font-medium text-[#0d0d0d]">AI Memory is {currentUser.memory_enabled ? 'ON' : 'OFF'}</p>
              <p className="text-[11px] text-[#5d5d5d]">
                {currentUser.memory_enabled 
                  ? "VietraAI will learn from your conversations." 
                  : "VietraAI will not store new facts or use past memories."}
              </p>
            </div>
            <button
              onClick={handleToggleConsent}
              disabled={isSavingConsent}
              className="flex items-center gap-2 px-3 py-1.5 rounded-[10px] bg-white border border-[#0000001a] text-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              {isSavingConsent ? (
                <Loader2 className="w-4 h-4 animate-spin text-[#0d0d0d]" />
              ) : currentUser.memory_enabled ? (
                <ToggleRight className="w-6 h-6 text-green-600 stroke-[1.5]" />
              ) : (
                <ToggleLeft className="w-6 h-6 text-[#8f8f8f] stroke-[1.5]" />
              )}
              <span className="font-medium text-[#0d0d0d]">
                {currentUser.memory_enabled ? 'Enabled' : 'Disabled'}
              </span>
            </button>
          </div>
        )}

        {/* Facts List Container */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-2 custom-scrollbar my-2">
          {isLoading ? (
            <div className="py-8 text-center text-[#5d5d5d] text-xs flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-[#0d0d0d] stroke-[1.75]" />
              <span>Loading AI memory...</span>
            </div>
          ) : facts.length === 0 ? (
            <div className="py-8 text-center border border-dashed border-[#0000001a] rounded-[10px] p-4 bg-[#f9f9f9]">
              <FolderX className="w-8 h-8 text-[#8f8f8f] mx-auto mb-2 stroke-[1.5]" />
              <p className="text-xs text-[#5d5d5d]">No remembered facts yet.</p>
              <p className="text-[11px] text-[#8f8f8f] mt-1">Chat with VietraAI to automatically remember your preferences!</p>
            </div>
          ) : (
            facts.map((fact) => (
              <div
                key={fact.id}
                className="bg-[#f9f9f9] border border-[#0000001a] hover:bg-[#0000000d] p-3 rounded-[10px] flex items-center justify-between transition-colors group"
              >
                <div className="flex items-start gap-3">
                  <span className="px-2 py-0.5 bg-[#e6e6e6] text-[#0d0d0d] text-[10px] font-semibold uppercase tracking-wide rounded-none mt-0.5">
                    {fact.fact_type}
                  </span>
                  <div>
                    <p className="text-sm text-[#0d0d0d] font-medium">{fact.fact_value}</p>
                    <p className="text-[11px] text-[#8f8f8f] font-mono mt-0.5">Key: {fact.fact_key}</p>
                  </div>
                </div>

                <button
                  onClick={() => handleDelete(fact.id)}
                  title="Delete this fact"
                  className="p-1 text-[#8f8f8f] hover:text-[#0d0d0d] hover:bg-[#0000000d] rounded-[10px] transition-colors shrink-0 cursor-pointer"
                >
                  <Trash2 className="w-4 h-4 stroke-[1.75]" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer info */}
        <div className="pt-3 border-t border-[#0000001a] mt-2 flex justify-between items-center text-xs text-[#5d5d5d]">
          <span>Total facts: {facts.length}</span>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#0d0d0d] hover:bg-[#000000] text-white rounded-[10px] text-xs font-medium transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
