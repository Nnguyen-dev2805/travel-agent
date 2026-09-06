import React, { useState, useEffect, useCallback } from 'react';
import ItineraryTimeline from './ItineraryTimeline';
import {
  Calendar,
  CheckCircle2,
  Clock,
  Layers,
  Sparkles,
  Award,
  RefreshCw,
} from 'lucide-react';
import {
  listItineraries,
  getItinerary,
  acceptItinerary,
  listDecisions,
} from '../../services/planner';

const STATUS_BADGE = {
  accepted: {
    label: 'Đã Phê Duyệt',
    color: 'bg-teal-100 text-teal-800 border-teal-300',
    icon: CheckCircle2,
  },
  proposed: {
    label: 'Đề Xuất',
    color: 'bg-amber-100 text-amber-800 border-amber-300',
    icon: Sparkles,
  },
  draft: {
    label: 'Bản Nháp',
    color: 'bg-stone-100 text-stone-700 border-stone-300',
    icon: Clock,
  },
  superseded: {
    label: 'Đã Thay Thế',
    color: 'bg-stone-100 text-stone-400 border-stone-200 line-through',
    icon: Clock,
  },
};

export default function PlannerPanel({ workspaceId, reloadTrigger }) {
  const [itineraries, setItineraries] = useState([]);
  const [activeVersion, setActiveVersion] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isAccepting, setIsAccepting] = useState(false);

  const fetchPlannerData = useCallback(async () => {
    if (!workspaceId) return;
    setIsLoading(true);
    try {
      const [versionsData, decisionsData] = await Promise.all([
        listItineraries(workspaceId),
        listDecisions(workspaceId),
      ]);

      setItineraries(versionsData || []);
      setDecisions(decisionsData || []);

      if (versionsData && versionsData.length > 0) {
        const accepted = versionsData.find((v) => v.status === 'accepted');
        const latest = versionsData[versionsData.length - 1];
        const target = accepted || latest;

        const fullVersion = await getItinerary(
          workspaceId,
          target.itinerary_version_id
        );
        setActiveVersion(fullVersion);
      } else {
        setActiveVersion(null);
      }
    } catch (err) {
      console.error('Lỗi tải dữ liệu Planner:', err);
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchPlannerData();
  }, [fetchPlannerData, reloadTrigger]);

  const handleSelectVersion = async (versionId) => {
    try {
      setIsLoading(true);
      const full = await getItinerary(workspaceId, versionId);
      setActiveVersion(full);
    } catch (err) {
      console.error('Lỗi chọn phiên bản:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcceptVersion = async () => {
    if (!activeVersion || isAccepting) return;
    try {
      setIsAccepting(true);
      await acceptItinerary(workspaceId, activeVersion.itinerary_version_id);
      await fetchPlannerData();
    } catch (err) {
      console.error('Lỗi phê duyệt phiên bản:', err);
    } finally {
      setIsAccepting(false);
    }
  };

  const statusConfig =
    STATUS_BADGE[activeVersion?.status] || STATUS_BADGE.draft;
  const StatusIcon = statusConfig.icon;

  return (
    <div className="w-full lg:w-96 xl:w-[420px] bg-surface-card border-l border-surface-border flex flex-col h-full shrink-0 shadow-xs">
      {/* Panel Header */}
      <div className="h-16 px-5 border-b border-surface-border flex items-center justify-between bg-surface-muted/30">
        <div className="flex items-center gap-2">
          <Calendar className="w-5 h-5 text-terracotta" />
          <h2 className="font-bold text-sm text-stone-900">
            Lịch Trình Chi Tiết
          </h2>
        </div>

        <button
          type="button"
          onClick={fetchPlannerData}
          disabled={isLoading}
          title="Tải lại kế hoạch"
          className="p-1.5 rounded-lg text-stone-400 hover:text-stone-700 hover:bg-stone-200/50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Version Selector Bar */}
      {itineraries.length > 0 && activeVersion && (
        <div className="p-4 border-b border-surface-border bg-surface-muted/20 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-stone-400" />
              <select
                value={activeVersion.itinerary_version_id}
                onChange={(e) => handleSelectVersion(e.target.value)}
                className="text-xs font-bold text-stone-800 bg-white border border-surface-border rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-terracotta"
              >
                {itineraries.map((v) => (
                  <option key={v.itinerary_version_id} value={v.itinerary_version_id}>
                    Phiên bản v{v.version_number} ({v.title || 'Lịch trình'})
                  </option>
                ))}
              </select>
            </div>

            {/* Status Badge */}
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${statusConfig.color}`}
            >
              <StatusIcon className="w-3.5 h-3.5" />
              <span>{statusConfig.label}</span>
            </span>
          </div>

          {/* Accept Button if not yet accepted */}
          {activeVersion.status !== 'accepted' && (
            <button
              type="button"
              disabled={isAccepting}
              onClick={handleAcceptVersion}
              className="w-full py-2 px-3 rounded-xl bg-teal hover:bg-teal-hover text-white text-xs font-bold shadow-xs hover:shadow transition-all flex items-center justify-center gap-1.5 disabled:opacity-60"
            >
              <Award className="w-4 h-4" />
              <span>
                {isAccepting ? 'Đang phê duyệt...' : 'Phê duyệt phiên bản này'}
              </span>
            </button>
          )}

          {activeVersion.summary && (
            <p className="text-xs text-stone-600 font-serif leading-relaxed italic bg-white/70 p-2.5 rounded-lg border border-surface-border/60">
              &ldquo;{activeVersion.summary}&rdquo;
            </p>
          )}
        </div>
      )}

      {/* Main Itinerary Content Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {itineraries.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-stone-400 space-y-3">
            <div className="w-12 h-12 rounded-xl bg-surface-muted flex items-center justify-center text-stone-400">
              <Calendar className="w-6 h-6" />
            </div>
            <h4 className="font-bold text-sm text-stone-700">
              Chưa có lịch trình nào
            </h4>
            <p className="text-xs text-stone-500 max-w-xs">
              Hãy yêu cầu AI trong khung chat: &ldquo;Lên lịch trình 3 ngày...&rdquo;, hệ thống sẽ tự động tổng hợp và hiển thị tại đây!
            </p>
          </div>
        ) : (
          <>
            {/* Itinerary Timeline */}
            <ItineraryTimeline items={activeVersion?.items || []} />

            {/* Confirmed Trip Decisions Section */}
            {decisions.length > 0 && (
              <div className="pt-4 border-t border-surface-border space-y-2.5">
                <h4 className="text-xs font-bold uppercase tracking-wider text-stone-500 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-teal" />
                  <span>Các quyết định đã chốt ({decisions.length})</span>
                </h4>
                <div className="space-y-1.5">
                  {decisions.map((dec) => (
                    <div
                      key={dec.decision_id}
                      className="p-2.5 rounded-lg bg-surface-muted/50 border border-surface-border text-xs text-stone-700 space-y-1"
                    >
                      <div className="font-semibold text-stone-800">
                        {dec.statement}
                      </div>
                      {dec.rationale && (
                        <div className="text-[11px] text-stone-500 font-serif">
                          {dec.rationale}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
