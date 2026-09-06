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
    color: 'bg-amber-100 text-amber-800 border-amber-200',
  },
  lodging: {
    label: 'Chỗ ở',
    icon: Hotel,
    color: 'bg-teal-100 text-teal-800 border-teal-200',
  },
  transport: {
    label: 'Di chuyển',
    icon: Navigation,
    color: 'bg-blue-100 text-blue-800 border-blue-200',
  },
  activity: {
    label: 'Tham quan',
    icon: Camera,
    color: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  },
  free_time: {
    label: 'Tự do',
    icon: Coffee,
    color: 'bg-purple-100 text-purple-800 border-purple-200',
  },
  note: {
    label: 'Ghi chú',
    icon: FileText,
    color: 'bg-stone-100 text-stone-800 border-stone-200',
  },
};

export default function ItineraryItemCard({ item }) {
  const config = ITEM_TYPE_CONFIG[item.item_type] || ITEM_TYPE_CONFIG.activity;
  const IconComponent = config.icon;

  return (
    <div className="group relative bg-surface-card rounded-xl p-3.5 border border-surface-border shadow-xs hover:shadow-md hover:border-terracotta/40 transition-all">
      <div className="flex items-start gap-3">
        {/* Type Icon */}
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border ${config.color}`}>
          <IconComponent className="w-4 h-4" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-semibold text-sm text-stone-900 leading-snug truncate">
              {item.title}
            </h4>
            {item.start_time && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-stone-500 font-mono shrink-0">
                <Clock className="w-3 h-3 text-stone-400" />
                {item.start_time}
                {item.end_time ? ` - ${item.end_time}` : ''}
              </span>
            )}
          </div>

          {item.location && (
            <div className="flex items-center gap-1 text-xs text-stone-500 truncate">
              <MapPin className="w-3 h-3 text-terracotta shrink-0" />
              <span className="truncate">{item.location}</span>
            </div>
          )}

          {item.notes && (
            <p className="text-xs text-stone-600 font-serif leading-relaxed mt-1 line-clamp-2">
              {item.notes}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
