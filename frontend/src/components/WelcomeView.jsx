import React from 'react';

export default function WelcomeView({ onSelectCard }) {
  const cards = [
    {
      title: 'Khám phá Rooftop Bars',
      desc: 'Top 7 rooftop bars ngắm cảnh tuyệt đẹp ở Nha Trang & Sài Gòn',
      icon: 'explore',
      query: 'Top 7 rooftop bars ngắm cảnh đẹp ở Việt Nam là những quán nào?',
    },
    {
      title: 'Lịch trình du lịch Hội An - Đà Nẵng',
      desc: 'Tư vấn lịch trình khám phá di sản văn hóa 3 ngày 2 đêm',
      icon: 'calendar_month',
      query: 'Tư vấn lịch trình du lịch Hội An và Đà Nẵng trong 3 ngày',
    },
    {
      title: 'Ẩm thực phố cổ Hà Nội',
      desc: 'Gợi ý những món ăn đặc sản truyền thống không thể bỏ qua',
      icon: 'restaurant',
      query: 'Những món ăn ngon truyền thống nhất phải thử ở Hà Nội là gì?',
    },
    {
      title: 'Nghỉ dưỡng & Biển đảo Phú Quốc',
      desc: 'Thời điểm đẹp nhất và kinh nghiệm du lịch đảo Ngọc',
      icon: 'flight_takeoff',
      query: 'Kinh nghiệm và thời điểm du lịch biển Phú Quốc đẹp nhất trong năm',
    },
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 text-center max-w-3xl mx-auto w-full">
      {/* Travel Agent Sparkle Badge */}
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-[#10a37f] to-[#1a7f64] flex items-center justify-center mb-6 shadow-xl shadow-[#10a37f]/20 border border-emerald-400/30 transform hover:scale-105 transition-transform duration-300">
        <span className="material-symbols-outlined text-white text-3xl">auto_awesome</span>
      </div>

      <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white mb-2">
        Bạn muốn khám phá địa điểm nào ở Việt Nam hôm nay?
      </h1>
      <p className="text-sm text-gray-400 mb-8 max-w-md">
        Trợ lý AI Du lịch được kết nối trực tiếp với CSDL Cẩm nang Du lịch Việt Nam (RAG Engine).
      </p>

      {/* Suggestion Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
        {cards.map((card, idx) => (
          <div
            key={idx}
            onClick={() => onSelectCard(card.query)}
            className="group p-4.5 rounded-2xl bg-[#2f2f2f] hover:bg-[#383838] border border-[#424242] hover:border-[#10a37f] cursor-pointer text-left transition-all duration-200 hover:scale-[1.02] shadow-md hover:shadow-emerald-950/20"
          >
            <div className="flex items-center gap-2.5 mb-1.5">
              <div className="w-7 h-7 rounded-lg bg-[#10a37f]/20 text-[#10a37f] flex items-center justify-center group-hover:bg-[#10a37f] group-hover:text-white transition-colors">
                <span className="material-symbols-outlined text-base">
                  {card.icon}
                </span>
              </div>
              <h3 className="font-semibold text-white text-sm group-hover:text-[#10a37f] transition-colors">
                {card.title}
              </h3>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed pl-9">{card.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
