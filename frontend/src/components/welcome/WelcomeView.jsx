import React from 'react';
import { Sparkles, MapPin, Calendar, ArrowRight, Plus } from 'lucide-react';

const STARTER_TRIPS = [
  {
    id: 'hagiang-3d2n',
    title: 'Hành Trình Mùa Hoa Hà Giang',
    destination_scope: 'Hà Giang, Đồng Văn, Mèo Vạc',
    duration: '3 ngày 2 đêm',
    tag: 'Phiêu Lưu & Cảnh Đẹp',
    tagColor: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    description: 'Chinh phục đèo Mã Pí Lèng huyền thoại, ngắm hoa tam giác mạch và khám phá phố cổ Đồng Văn.',
    prompt: 'Tôi muốn lên kế hoạch đi Hà Giang 3 ngày 2 đêm xuất phát từ Hà Nội, ưu tiên ngắm cảnh đèo Mã Pí Lèng và thưởng thức ẩm thực vùng cao.',
  },
  {
    id: 'danang-hoian-4d3n',
    title: 'Food Tour Đà Nẵng & Phố Cổ Hội An',
    destination_scope: 'Đà Nẵng, Hội An, Quảng Nam',
    duration: '4 ngày 3 đêm',
    tag: 'Ẩm Thực & Di Sản',
    tagColor: 'bg-amber-100 text-amber-800 border-amber-200',
    description: 'Thưởng thức mì Quảng, cao lầu, thả đèn hoa đăng sông Hoài và tắm biển Mỹ Khê trong xanh.',
    prompt: 'Lên lịch trình 4 ngày 3 đêm kết hợp Đà Nẵng và Hội An, chú trọng trải nghiệm ẩm thực đặc sản địa phương và nghỉ dưỡng thư thái.',
  },
  {
    id: 'phuquoc-3d2n',
    title: 'Nghỉ Dưỡng Thiên Đường Biển Phú Quốc',
    destination_scope: 'Phú Quốc, Kiên Giang',
    duration: '3 ngày 2 đêm',
    tag: 'Biển Đảo & Thư Giãn',
    tagColor: 'bg-teal-100 text-teal-800 border-teal-200',
    description: 'Ngắm hoàng hôn lãng mạn tại Sunset Sanato, lặn ngắm san hô quần đảo An Thới và chợ đêm Dinh Cậu.',
    prompt: 'Tư vấn cho tôi lịch trình 3 ngày 2 đêm nghỉ dưỡng tại Phú Quốc cho cặp đôi, thích biển đẹp, ngắm hoàng hôn và hải sản tươi ngon.',
  },
];

export default function WelcomeView({ onSelectTemplate, onOpenCreateModal }) {
  return (
    <div className="flex-1 overflow-y-auto p-6 lg:p-12 flex flex-col items-center justify-center bg-surface-base">
      <div className="max-w-4xl w-full space-y-10 animate-fade-in">
        {/* Hero Section */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-terracotta/10 border border-terracotta/20 text-terracotta text-xs font-semibold shadow-xs">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Trợ Lý Du Lịch AI Am Hiểu Địa Phương</span>
          </div>
          <h1 className="text-3xl lg:text-5xl font-extrabold text-stone-900 tracking-tight leading-tight">
            Khám Phá Vẻ Đẹp <span className="text-terracotta">Việt Nam</span>
          </h1>
          <p className="text-stone-600 text-sm lg:text-base max-w-xl mx-auto leading-relaxed">
            Chọn một hành trình gợi ý bên dưới hoặc tạo chuyến đi tùy chỉnh. Trợ lý AI sẽ giúp bạn lập lịch trình từng ngày, gợi ý món ngon và theo dõi kế hoạch thông minh.
          </p>
        </div>

        {/* 1-Click Starter Cards Grid */}
        <div className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-sm font-bold uppercase tracking-wider text-stone-500">
              Khởi động nhanh trong 1-Click
            </h2>
            <button
              type="button"
              onClick={onOpenCreateModal}
              className="text-xs font-semibold text-terracotta hover:underline flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Tạo chuyến đi tùy chỉnh</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {STARTER_TRIPS.map((trip) => (
              <div
                key={trip.id}
                onClick={() => onSelectTemplate(trip)}
                className="group relative bg-surface-card border border-surface-border rounded-2xl p-5 shadow-sm hover:shadow-xl hover:border-terracotta/50 transition-all duration-300 cursor-pointer flex flex-col justify-between"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md border ${trip.tagColor}`}>
                      {trip.tag}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-stone-400 font-medium">
                      <Calendar className="w-3 h-3" />
                      {trip.duration}
                    </span>
                  </div>

                  <h3 className="font-bold text-base text-stone-900 group-hover:text-terracotta transition-colors leading-snug">
                    {trip.title}
                  </h3>

                  <div className="flex items-center gap-1.5 text-xs text-teal font-medium">
                    <MapPin className="w-3.5 h-3.5 shrink-0" />
                    <span className="truncate">{trip.destination_scope}</span>
                  </div>

                  <p className="text-xs text-stone-500 line-clamp-3 leading-relaxed">
                    {trip.description}
                  </p>
                </div>

                <div className="pt-4 mt-4 border-t border-surface-border/60 flex items-center justify-between text-xs font-semibold text-terracotta">
                  <span>Khởi tạo ngay</span>
                  <ArrowRight className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
