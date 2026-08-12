import React from 'react';

export default function WelcomeView() {
  return (
    <div className="flex-1 w-full max-w-[768px] px-6 py-12 flex flex-col justify-center items-center overflow-y-auto mx-auto">
      {/* Title */}
      <h2 className="text-3xl md:text-4xl font-bold text-white text-center max-w-[600px] leading-tight">
        How can I help you with your travels today?
      </h2>
    </div>
  );
}
