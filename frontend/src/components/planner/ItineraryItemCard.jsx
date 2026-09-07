import React from 'react';
import {
  Utensils,
  Hotel,
  Navigation,
  Camera,
  Coffee,
  FileText,
  MapPin,
  Clock,
} from 'lucide-react';

const ITEM_TYPE_CONFIG = {
  meal: {
    label: 'Ăn uống',
    icon: Utensils,
  },
  lodging: {
    label: 'Chỗ ở',
    icon: Hotel,
  },
  transport: {
    label: 'Di chuyển',
    icon: Navigation,
  },
  activity: {
    label: 'Tham quan',
    icon: Camera,
  },
  free_time: {
    label: 'Tự do',
    icon: Coffee,
  },
  note: {
    label: 'Ghi chú',
    icon: FileText,
  },
};

export default function ItineraryItemCard({ item }) {
  const config = ITEM_TYPE_CONFIG[item.item_type] || ITEM_TYPE_CONFIG.activity;
  const IconComponent = config.icon;

  return (
    <div className="group relative bg-pure-white rounded-lg p-3.5 border border-hairline hover:bg-hover-veil transition-colors font-sans">
      <div className="flex items-start gap-3">
        {/* Type Icon: Minimalist monochrome */}
        <div className="w-7 h-7 rounded border border-hairline bg-sidebar-mist flex items-center justify-center shrink-0 text-graphite-ink">
          <IconComponent className="w-3.5 h-3.5 stroke-[1.8]" aria-hidden="true" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-medium text-caption text-graphite-ink leading-snug truncate">
              {item.title}
            </h4>
            {item.start_time && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-mid-ash font-mono shrink-0">
                <Clock className="w-3 h-3 text-mid-ash" aria-hidden="true" />
                {item.start_time}
                {item.end_time ? ` - ${item.end_time}` : ''}
              </span>
            )}
          </div>

          {item.location && (
            <div className="flex items-center gap-1 text-[12px] text-mid-ash truncate">
              <MapPin className="w-3 h-3 text-mid-ash shrink-0" aria-hidden="true" />
              <span className="truncate">{item.location}</span>
            </div>
          )}

          {item.notes && (
            <p className="text-[12px] text-mid-ash leading-relaxed mt-1">
              {item.notes}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
