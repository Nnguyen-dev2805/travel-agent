import React, { useState, useEffect, useCallback } from 'react';
import ItineraryTimeline from './ItineraryTimeline';
import {
  Calendar,
  CheckCircle2,
  Clock,
  Sparkles,
  Layers,
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
    icon: CheckCircle2,
  },
  proposed: {
    label: 'Đề Xuất',
    icon: Sparkles,
  },
  draft: {
    label: 'Bản Nháp',
    icon: Clock,
  },
  superseded: {
    label: 'Đã Thay Thế',
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
        // Default to the first version (usually newest)
        const detailed = await getItinerary(
          workspaceId,
          versionsData[0].itinerary_version_id
        );
        setActiveVersion(detailed);
      } else {
        setActiveVersion(null);
      }
    } catch (err) {
      console.error('Lỗi khi tải dữ liệu kế hoạch:', err);
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
      const detailed = await getItinerary(workspaceId, versionId);
      setActiveVersion(detailed);
    } catch (err) {
      console.error('Lỗi khi xem chi tiết phiên bản:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcceptVersion = async () => {
    if (!activeVersion) return;
    try {
      setIsAccepting(true);
      await acceptItinerary(workspaceId, activeVersion.itinerary_version_id);
      await fetchPlannerData();
    } catch (err) {
      console.error('Lỗi khi phê duyệt lịch trình:', err);
    } finally {
      setIsAccepting(false);
    }
  };

  const statusConfig =
    STATUS_BADGE[activeVersion?.status] || STATUS_BADGE.draft;
  const StatusIcon = statusConfig.icon;

  return (
    <div className="w-full lg:w-96 xl:w-[420px] bg-pure-white border-l border-hairline flex flex-col h-full shrink-0 font-sans">
      {/* Panel Header */}
      <div className="h-[52px] px-5 border-b border-hairline flex items-center justify-between bg-pure-white">
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-graphite-ink stroke-[1.8]" aria-hidden="true" />
          <h2 className="font-semibold text-caption text-graphite-ink">
            Lịch Trình Chi Tiết
          </h2>
        </div>

        <button
          type="button"
          onClick={fetchPlannerData}
          disabled={isLoading}
          title="Tải lại kế hoạch"
          aria-label="Tải lại kế hoạch"
          className="p-1.5 rounded-lg text-mid-ash hover:text-graphite-ink hover:bg-hover-veil transition-colors disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} aria-hidden="true" />
        </button>
      </div>

      {/* Version Selector Bar */}
      {itineraries.length > 0 && activeVersion && (
        <div className="p-4 border-b border-hairline bg-sidebar-mist space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-mid-ash" aria-hidden="true" />
              <select
                aria-label="Chọn phiên bản lịch trình"
                value={activeVersion.itinerary_version_id}
                onChange={(e) => handleSelectVersion(e.target.value)}
                className="text-[12px] font-medium text-graphite-ink bg-pure-white border border-hairline rounded-lg px-2.5 py-1 focus:outline-none focus:ring-1 focus:ring-graphite-ink"
              >
                {itineraries.map((v) => (
                  <option key={v.itinerary_version_id} value={v.itinerary_version_id}>
                    Phiên bản v{v.version_number} ({v.title || 'Lịch trình'})
                  </option>
                ))}
              </select>
            </div>

            {/* Status Badge */}
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-hairline bg-pure-white text-[11px] font-medium text-graphite-ink">
              <StatusIcon className="w-3 h-3 text-graphite-ink" aria-hidden="true" />
              <span>{statusConfig.label}</span>
            </span>
          </div>

          {/* Accept Button if not yet accepted */}
          {activeVersion.status !== 'accepted' && (
            <button
              type="button"
              disabled={isAccepting}
              onClick={handleAcceptVersion}
              className="w-full py-2 px-3 rounded-lg bg-graphite-ink hover:bg-black text-pure-white text-[12px] font-medium transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
            >
              <Award className="w-3.5 h-3.5" aria-hidden="true" />
              <span>
                {isAccepting ? 'Đang phê duyệt…' : 'Phê duyệt phiên bản này'}
              </span>
            </button>
          )}

          {activeVersion.summary && (
            <p className="text-[12px] text-mid-ash leading-relaxed italic bg-pure-white p-2.5 rounded-lg border border-hairline">
              &ldquo;{activeVersion.summary}&rdquo;
            </p>
          )}
        </div>
      )}

      {/* Main Itinerary Content Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {itineraries.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-mid-ash space-y-3">
            <div className="w-10 h-10 rounded-lg border border-hairline bg-sidebar-mist flex items-center justify-center text-graphite-ink">
              <Calendar className="w-5 h-5 stroke-[1.8]" aria-hidden="true" />
            </div>
            <h4 className="font-semibold text-caption text-graphite-ink">
              Chưa có lịch trình nào
            </h4>
            <p className="text-[12px] text-mid-ash max-w-xs leading-relaxed">
              Hãy yêu cầu AI trong khung chat: &ldquo;Lên lịch trình 3 ngày…&rdquo;, hệ thống sẽ tự động tổng hợp và hiển thị tại đây!
            </p>
          </div>
        ) : (
          <>
            {/* Itinerary Timeline */}
            <ItineraryTimeline items={activeVersion?.items || []} />

            {/* Confirmed Trip Decisions Section */}
            {decisions.length > 0 && (
              <div className="pt-4 border-t border-hairline space-y-2.5">
                <h4 className="text-[11px] font-medium uppercase tracking-wider text-mid-ash flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-graphite-ink" aria-hidden="true" />
                  <span>Các quyết định đã chốt ({decisions.length})</span>
                </h4>
                <div className="space-y-1.5">
                  {decisions.map((dec) => (
                    <div
                      key={dec.decision_id}
                      className="p-2.5 rounded-lg bg-sidebar-mist border border-hairline text-[12px] text-graphite-ink space-y-0.5"
                    >
                      <div className="font-medium text-graphite-ink">
                        {dec.statement}
                      </div>
                      {dec.rationale && (
                        <div className="text-[11px] text-mid-ash">
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
