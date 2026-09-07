import React from 'react';
import { MapPin, Calendar, ArrowRight, Plus } from 'lucide-react';

const STARTER_TRIPS = [
  {
    id: 'hagiang-3d2n',
    title: 'Hành Trình Mùa Hoa Hà Giang',
    destination_scope: 'Hà Giang, Đồng Văn, Mèo Vạc',
    duration: '3 ngày 2 đêm',
    tag: 'Phiêu Lưu & Cảnh Đẹp',
    description: 'Chinh phục đèo Mã Pí Lèng huyền thoại, ngắm hoa tam giác mạch và khám phá phố cổ Đồng Văn.',
    prompt: 'Tôi muốn lên kế hoạch đi Hà Giang 3 ngày 2 đêm xuất phát từ Hà Nội, ưu tiên ngắm cảnh đèo Mã Pí Lèng và thưởng thức ẩm thực vùng cao.',
  },
  {
    id: 'danang-hoian-4d3n',
    title: 'Food Tour Đà Nẵng & Phố Cổ Hội An',
    destination_scope: 'Đà Nẵng, Hội An, Quảng Nam',
    duration: '4 ngày 3 đêm',
    tag: 'Ẩm Thực & Di Sản',
    description: 'Thưởng thức mì Quảng, cao lầu, thả đèn hoa đăng sông Hoài và tắm biển Mỹ Khê trong xanh.',
    prompt: 'Lên lịch trình 4 ngày 3 đêm kết hợp Đà Nẵng và Hội An, chú trọng trải nghiệm ẩm thực đặc sản địa phương và nghỉ dưỡng thư thái.',
  },
  {
    id: 'phuquoc-3d2n',
    title: 'Nghỉ Dưỡng Thiên Đường Biển Phú Quốc',
    destination_scope: 'Phú Quốc, Kiên Giang',
    duration: '3 ngày 2 đêm',
    tag: 'Biển Đảo & Thư Giãn',
    description: 'Ngắm hoàng hôn lãng mạn tại Sunset Sanato, lặn ngắm san hô quần đảo An Thới và chợ đêm Dinh Cậu.',
    prompt: 'Tư vấn cho tôi lịch trình 3 ngày 2 đêm nghỉ dưỡng tại Phú Quốc cho cặp đôi, thích biển đẹp, ngắm hoàng hôn và hải sản tươi ngon.',
  },
];

export default function WelcomeView({ onSelectTemplate, onOpenCreateModal }) {
  return (
    <div className="flex-1 overflow-y-auto p-6 lg:p-12 flex flex-col items-center justify-center bg-pure-white font-sans">
      <div className="max-w-3xl w-full space-y-8 animate-fade-in">
        {/* Hero Section */}
        <div className="text-center space-y-2">
          <h1 className="text-[30px] sm:text-[34px] font-medium text-graphite-ink tracking-tight text-balance">
            Where should we begin?
          </h1>
          <p className="text-caption text-mid-ash max-w-md mx-auto leading-relaxed text-pretty">
            Chọn một hành trình gợi ý bên dưới hoặc tạo chuyến đi mới để bắt đầu.
          </p>
        </div>

        {/* Starter Cards Grid */}
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-caption font-medium uppercase tracking-wider text-mid-ash">
              Khởi động nhanh trong 1-Click
            </h2>
            <button
              type="button"
              onClick={onOpenCreateModal}
              className="text-caption font-medium text-graphite-ink hover:underline flex items-center gap-1 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none rounded"
            >
              <Plus className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Tạo chuyến đi mới</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {STARTER_TRIPS.map((trip) => (
              <button
                key={trip.id}
                type="button"
                onClick={() => onSelectTemplate(trip)}
                className="p-4 rounded-lg bg-pure-white border border-hairline hover:bg-hover-veil transition-colors text-left group cursor-pointer flex flex-col justify-between focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
              >
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium px-2 py-0.5 rounded border border-hairline bg-sidebar-mist text-graphite-ink">
                      {trip.tag}
                    </span>
                    <span className="flex items-center gap-1 text-[11px] text-mid-ash">
                      <Calendar className="w-3 h-3" aria-hidden="true" />
                      {trip.duration}
                    </span>
                  </div>

                  <h3 className="font-semibold text-caption text-graphite-ink leading-snug">
                    {trip.title}
                  </h3>

                  <div className="flex items-center gap-1.5 text-[12px] text-mid-ash">
                    <MapPin className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                    <span className="truncate">{trip.destination_scope}</span>
                  </div>

                  <p className="text-[12px] text-mid-ash leading-relaxed">
                    {trip.description}
                  </p>
                </div>

                <div className="pt-3 mt-3 border-t border-hairline flex items-center justify-between text-caption font-medium text-graphite-ink">
                  <span>Khởi tạo ngay</span>
                  <ArrowRight className="w-3.5 h-3.5 transform group-hover:translate-x-1 transition-transform" aria-hidden="true" />
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
