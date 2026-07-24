import React from 'react';

export default function WelcomeView({ onSelectCard }) {
  const cards = [
    {
      title: 'Hỏi về địa điểm du lịch',
      desc: 'Top 7 rooftop bars ở Sài Gòn hoặc quán cà phê đẹp ở Hà Nội',
      icon: 'explore',
    },
    {
      title: 'Lên lịch trình 3 ngày',
      desc: 'Tạo lịch trình tham quan văn hóa tại Hội An và Đà Nẵng',
      icon: 'calendar_month',
    },
    {
      title: 'Khám phá ẩm thực',
      desc: 'Gợi ý những món ăn phải thử khi đến Hà Giang và Phú Quốc',
      icon: 'restaurant',
    },
    {
      title: 'Mẹo di chuyển & Khách sạn',
      desc: 'Tư vấn phương tiện di chuyển và thời điểm đi du lịch đẹp nhất',
      icon: 'flight_takeoff',
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-3xl mx-auto w-full">
      {/* ChatGPT Icon Sparkle */}
      <div className="w-12 h-12 rounded-full bg-[#10a37f] flex items-center justify-center mb-6 shadow-lg shadow-[#10a37f]/20">
        <span className="material-symbols-outlined text-white text-2xl">auto_awesome</span>
      </div>

      <h1 className="text-2xl md:text-3xl font-semibold text-white mb-8">
        What can I help with today?
      </h1>

      {/* Suggestion Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
        {cards.map((card, idx) => (
          <div
            key={idx}
            onClick={() => onSelectCard(card.title)}
            className="p-4 rounded-xl bg-[#2f2f2f] hover:bg-[#383838] border border-[#424242] cursor-pointer text-left transition-all hover:scale-[1.01]"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="material-symbols-outlined text-[#10a37f] text-sm">
                {card.icon}
              </span>
              <h3 className="font-semibold text-white text-sm">{card.title}</h3>
            </div>
            <p className="text-xs text-gray-400">{card.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
