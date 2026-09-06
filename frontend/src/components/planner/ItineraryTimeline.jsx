import React from 'react';
import ItineraryItemCard from './ItineraryItemCard';
import { Calendar, Compass } from 'lucide-react';

export default function ItineraryTimeline({ items = [] }) {
  if (!items || items.length === 0) {
    return (
      <div className="p-8 text-center text-stone-400 space-y-2">
        <Compass className="w-8 h-8 mx-auto opacity-40 text-terracotta" />
        <p className="text-xs">Chưa có hoạt động nào trong phiên bản lịch trình này.</p>
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
    <div className="space-y-6">
      {sortedDays.map((day) => {
        const dayItems = groupedByDay[day].sort(
          (a, b) => (a.position || 0) - (b.position || 0)
        );

        return (
          <div key={day} className="relative space-y-3">
            {/* Day Header */}
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold bg-terracotta text-white shadow-xs">
                <Calendar className="w-3.5 h-3.5" />
                <span>Ngày {day}</span>
              </span>
              <span className="text-xs text-stone-400 font-medium">
                ({dayItems.length} hoạt động)
              </span>
            </div>

            {/* Day Items List with vertical line */}
            <div className="relative pl-3 ml-3 border-l-2 border-surface-border space-y-3">
              {dayItems.map((item, idx) => (
                <div key={item.itinerary_item_id || idx} className="relative">
                  {/* Timeline Dot */}
                  <div className="absolute -left-[19px] top-4 w-2.5 h-2.5 rounded-full bg-terracotta border-2 border-white shadow-xs" />
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
