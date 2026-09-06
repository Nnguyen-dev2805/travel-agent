import React, { useState } from 'react';
import { KeyRound, UserCheck, Compass, Sparkles, ShieldCheck } from 'lucide-react';
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-stone-900/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md bg-surface-card rounded-2xl shadow-2xl border border-surface-border overflow-hidden transform transition-all">
        {/* Header Header Banner */}
        <div className="bg-gradient-to-r from-terracotta to-amber p-6 text-white text-center relative">
          <div className="w-16 h-16 mx-auto mb-3 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center shadow-inner">
            <Compass className="w-9 h-9 text-white animate-spin-slow" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Travel Agent AI</h2>
          <p className="text-sm text-white/90 mt-1 font-medium">
            Trợ lý Lên Lịch Trình Du Lịch Việt Nam Thông Minh
          </p>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 mt-3 rounded-full bg-white/25 text-xs font-medium">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Bảo mật Milestone R9 Authenticated</span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          {/* Quick Login Presets */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-500 mb-2.5">
              Đăng nhập thử nghiệm nhanh (Local Presets)
            </label>
            <div className="grid grid-cols-1 gap-2.5">
              {PRESET_USERS.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => handleSelectPreset(user)}
                  className="flex items-center justify-between p-3.5 rounded-xl border border-surface-border bg-surface-muted/60 hover:bg-terracotta/5 hover:border-terracotta/40 transition-all text-left group"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-white flex items-center justify-center shadow-sm text-stone-700 group-hover:text-terracotta transition-colors">
                      <UserCheck className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="font-semibold text-stone-800 text-sm">
                        {user.name}
                      </div>
                      <div className="text-xs text-stone-500 font-mono">
                        {user.token}
                      </div>
                    </div>
                  </div>
                  <span className="text-xs font-medium text-terracotta opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                    Vào ngay <Sparkles className="w-3.5 h-3.5" />
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="relative flex py-1 items-center">
            <div className="flex-grow border-t border-surface-border"></div>
            <span className="flex-shrink mx-3 text-xs font-medium text-stone-400 uppercase tracking-wider">
              Hoặc dùng Custom Token
            </span>
            <div className="flex-grow border-t border-surface-border"></div>
          </div>

          {/* Manual Token Form */}
          <form onSubmit={handleCustomSubmit} className="space-y-3">
            <div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-stone-400">
                  <KeyRound className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Nhập Bearer Token (ví dụ: token_alice_secret)..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-surface-border bg-white text-sm focus:outline-none focus:ring-2 focus:ring-terracotta/40 focus:border-terracotta text-stone-800 placeholder-stone-400 transition-all"
                />
              </div>
              {error && (
                <p className="text-xs text-red-600 mt-1.5 font-medium ml-1">
                  {error}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="w-full py-2.5 px-4 rounded-xl bg-terracotta hover:bg-terracotta-hover text-white font-medium text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2"
            >
              <span>Xác nhận Token</span>
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-surface-muted border-t border-surface-border/60 text-center">
          <p className="text-xs text-stone-500">
            Token được lưu trong trình duyệt của bạn (localStorage).
          </p>
        </div>
      </div>
    </div>
  );
}
