import React, { useState } from 'react';
import { KeyRound, UserCheck, Compass, ShieldCheck } from 'lucide-react';
import { PRESET_USERS, setToken } from '../../services/auth';

export default function LoginModal({ onLoginSuccess }) {
  const [tokenInput, setTokenInput] = useState('');
  const [error, setError] = useState('');

  const handleCustomSubmit = (e) => {
    e.preventDefault();
    if (!tokenInput.trim()) {
      setError('Vui lòng nhập Bearer Token để tiếp tục.');
      return;
    }
    setToken(tokenInput);
    setError('');
    onLoginSuccess();
  };

  const handleSelectPreset = (preset) => {
    setToken(preset.token, preset.name);
    setError('');
    onLoginSuccess();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 font-sans"
    >
      {/* Scrim Backdrop */}
      <div className="fixed inset-0 bg-[#00000080]" aria-hidden="true" />

      {/* Modal Card: Solid Pure White */}
      <div className="relative z-10 w-full max-w-md bg-white rounded-lg border border-hairline overflow-hidden">
        {/* Header: Pure White, Minimalist */}
        <div className="p-6 border-b border-hairline text-center bg-white">
          <div className="w-10 h-10 mx-auto mb-3 rounded-lg border border-hairline bg-sidebar-mist flex items-center justify-center text-graphite-ink">
            <Compass className="w-5 h-5 stroke-[1.8]" aria-hidden="true" />
          </div>
          <h2 id="login-modal-title" className="text-heading font-semibold text-graphite-ink tracking-tight">
            Travel Agent AI
          </h2>
          <p className="text-caption text-mid-ash mt-1">
            Trợ lý Lên Lịch Trình Du Lịch Việt Nam
          </p>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 mt-2 rounded border border-hairline bg-sidebar-mist text-[12px] font-medium text-mid-ash">
            <ShieldCheck className="w-3.5 h-3.5 text-graphite-ink" aria-hidden="true" />
            <span>Xác thực người dùng Milestone R9</span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5 bg-white">
          {/* Quick Login Presets */}
          <div>
            <span className="block text-[12px] font-medium text-mid-ash uppercase tracking-wider mb-2.5">
              Đăng nhập thử nghiệm nhanh (Local Presets)
            </span>
            <div className="grid grid-cols-1 gap-2">
              {PRESET_USERS.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => handleSelectPreset(user)}
                  className="flex items-center justify-between p-3 rounded-lg border border-hairline bg-white hover:bg-hover-veil transition-colors text-left group cursor-pointer focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg border border-hairline bg-sidebar-mist flex items-center justify-center text-graphite-ink">
                      <UserCheck className="w-4 h-4" aria-hidden="true" />
                    </div>
                    <div>
                      <div className="font-medium text-caption text-graphite-ink">
                        {user.name}
                      </div>
                      <div className="text-[11px] text-hollow font-mono">
                        {user.token}
                      </div>
                    </div>
                  </div>
                  <span className="text-caption font-medium text-mid-ash group-hover:text-graphite-ink transition-colors">
                    Chọn →
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-hairline"></div>
            <span className="flex-shrink mx-3 text-[11px] font-medium text-hollow uppercase tracking-wider">
              Hoặc dùng Custom Token
            </span>
            <div className="flex-grow border-t border-hairline"></div>
          </div>

          {/* Manual Token Form */}
          <form onSubmit={handleCustomSubmit} className="space-y-3">
            <div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-mid-ash">
                  <KeyRound className="w-4 h-4" aria-hidden="true" />
                </div>
                <input
                  type="text"
                  aria-label="Nhập Bearer Token"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Nhập Bearer Token (ví dụ: token_alice_secret)…"
                  className="w-full pl-9 pr-3.5 py-2 rounded-lg border border-hairline bg-white text-caption text-graphite-ink placeholder-hollow focus:outline-none focus:ring-1 focus:ring-graphite-ink focus:border-graphite-ink transition-colors"
                />
              </div>
              {error && (
                <p className="text-[12px] text-graphite-ink font-medium mt-1.5 ml-1">
                  {error}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="w-full py-2 px-4 rounded-lg bg-graphite-ink hover:bg-black text-white font-medium text-caption transition-colors flex items-center justify-center gap-2 focus-visible:ring-2 focus-visible:ring-graphite-ink focus-visible:outline-none"
            >
              <span>Xác nhận Token</span>
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="px-6 py-2.5 bg-sidebar-mist border-t border-hairline text-center">
          <p className="text-[12px] text-hollow">
            Token được lưu trong trình duyệt của bạn (localStorage).
          </p>
        </div>
      </div>
    </div>
  );
}
