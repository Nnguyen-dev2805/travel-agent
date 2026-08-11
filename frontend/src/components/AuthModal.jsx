import React, { useState } from 'react';
import { loginUser, registerUser, getCurrentUser } from '../services/api';

export default function AuthModal({ isOpen, onClose, onAuthSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setIsLoading(true);

    try {
      if (mode === 'register') {
        // Register user
        await registerUser(email, password, fullName);
        // Automatically login after successful registration
        await loginUser(email, password);
      } else {
        // Login user
        await loginUser(email, password);
      }

      // Fetch profile and notify parent
      const profile = await getCurrentUser();
      onAuthSuccess(profile);
      onClose();
    } catch (err) {
      setErrorMessage(err.message || 'Đã có lỗi xảy ra. Vui lòng thử lại!');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-md bg-[#1e1e1e] border border-[#383838] rounded-2xl p-6 shadow-2xl text-white overflow-hidden">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-[#2f2f2f] transition-colors"
        >
          <span className="material-symbols-outlined text-xl">close</span>
        </button>

        {/* Modal Header & Tabs */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-[#10a37f] to-[#1a7f64] mx-auto flex items-center justify-center shadow-lg shadow-[#10a37f]/20 mb-3">
            <span className="material-symbols-outlined text-2xl text-white">
              {mode === 'login' ? 'lock' : 'person_add'}
            </span>
          </div>
          <h2 className="text-xl font-bold tracking-tight text-white">
            {mode === 'login' ? 'Đăng nhập vào Travel Agent' : 'Tạo tài khoản mới'}
          </h2>
          <p className="text-xs text-gray-400 mt-1">
            Kích hoạt Long-term Memory để AI ghi nhớ sở thích du lịch cá nhân của bạn.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-[#141414] p-1 rounded-xl mb-5 border border-[#2a2a2a]">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setErrorMessage('');
            }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
              mode === 'login'
                ? 'bg-[#2a2a2a] text-white shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Đăng nhập
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('register');
              setErrorMessage('');
            }}
            className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
              mode === 'register'
                ? 'bg-[#2a2a2a] text-white shadow'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Đăng ký
          </button>
        </div>

        {/* Error Notification */}
        {errorMessage && (
          <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-base shrink-0">error</span>
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Form Inputs */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">Họ và tên</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nguyễn Văn A"
                className="w-full px-3.5 py-2.5 rounded-xl bg-[#141414] border border-[#333333] text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#10a37f] transition-all"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@travel.vn"
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#141414] border border-[#333333] text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#10a37f] transition-all"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Mật khẩu</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#141414] border border-[#333333] text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#10a37f] transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full mt-2 py-3 rounded-xl bg-[#10a37f] hover:bg-[#1a7f64] text-white font-semibold text-sm transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-[#10a37f]/20 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <span className="material-symbols-outlined text-base animate-spin">sync</span>
                <span>Đang xử lý...</span>
              </>
            ) : (
              <span>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}</span>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
