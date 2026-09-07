import React from 'react';
import ItineraryItemCard from './ItineraryItemCard';
import { Calendar, Compass } from 'lucide-react';

export default function ItineraryTimeline({ items = [] }) {
  if (!items || items.length === 0) {
    return (
      <div className="p-8 text-center text-mid-ash space-y-2 font-sans">
        <Compass className="w-8 h-8 mx-auto opacity-40 text-graphite-ink stroke-[1.5]" aria-hidden="true" />
        <p className="text-caption text-mid-ash">Chưa có hoạt động nào trong phiên bản lịch trình này.</p>
      </div>
    );
  }

  // Group items by day_index
  const groupedByDay = items.reduce((acc, item) => {
    const day = item.day_index || 1;
    if (!acc[day]) acc[day] = [];
    acc[day].push(item);
    return acc;
  }, {});

  // Sort by position inside day
  const sortedDays = Object.keys(groupedByDay)
    .map(Number)
    .sort((a, b) => a - b);

  return (
    <div className="space-y-6 font-sans">
      {sortedDays.map((day) => {
        const dayItems = groupedByDay[day].sort(
          (a, b) => (a.position || 0) - (b.position || 0)
        );

        return (
          <div key={day} className="relative space-y-3">
            {/* Day Header */}
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-hairline bg-sidebar-mist text-caption font-semibold text-graphite-ink">
                <Calendar className="w-3.5 h-3.5 stroke-[1.8]" aria-hidden="true" />
                <span>Ngày {day}</span>
              </span>
              <span className="text-[12px] text-mid-ash font-medium">
                ({dayItems.length} hoạt động)
              </span>
            </div>

            {/* Day Items List with vertical line */}
            <div className="relative pl-3 ml-3 border-l border-hairline space-y-2.5">
              {dayItems.map((item, idx) => (
                <div key={item.itinerary_item_id || idx} className="relative">
                  {/* Timeline Dot */}
                  <div className="absolute -left-[17px] top-4 w-2 h-2 rounded-full bg-graphite-ink" aria-hidden="true" />
                  <ItineraryItemCard item={item} />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
