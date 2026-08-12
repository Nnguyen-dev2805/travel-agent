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
        await registerUser(email, password, fullName);
        await loginUser(email, password);
      } else {
        await loginUser(email, password);
      }

      const profile = await getCurrentUser();
      onAuthSuccess(profile);
      onClose();
    } catch (err) {
      setErrorMessage(err.message || 'An error occurred. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#00000080] p-4 animate-in fade-in duration-200">
      <div className="bg-[#ffffff] border border-[#0000001a] rounded-[10px] w-full max-w-[440px] flex flex-col overflow-hidden relative text-[#0d0d0d]">
        {/* Close Icon */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-[#5d5d5d] hover:text-[#0d0d0d] p-1 transition-colors rounded-[10px] hover:bg-[#0000000d]"
        >
          <span className="material-symbols-outlined text-xl">close</span>
        </button>

        {/* Header Section */}
        <div className="px-8 pt-10 pb-6 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-[#f9f9f9] mb-4 border border-[#0000001a]">
            <span className="material-symbols-outlined text-[#0d0d0d] text-2xl">
              flight_takeoff
            </span>
          </div>
          <h2 className="text-[24px] font-semibold text-[#0d0d0d] mb-1.5 leading-[1.33]">
            VietraAI
          </h2>
          <p className="text-sm text-[#5d5d5d] leading-[1.43]">
            Welcome to VietraAI - Sign in or create an account to start your travel journey
          </p>
        </div>

        {/* Tabs */}
        <div className="px-8 flex border-b border-[#0000001a] mb-6">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setErrorMessage('');
            }}
            className={`flex-1 pb-3 text-sm font-medium transition-colors text-center cursor-pointer ${
              mode === 'login'
                ? 'text-[#0d0d0d] border-b-2 border-[#0d0d0d]'
                : 'text-[#5d5d5d] hover:text-[#0d0d0d]'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('register');
              setErrorMessage('');
            }}
            className={`flex-1 pb-3 text-sm font-medium transition-colors text-center cursor-pointer ${
              mode === 'register'
                ? 'text-[#0d0d0d] border-b-2 border-[#0d0d0d]'
                : 'text-[#5d5d5d] hover:text-[#0d0d0d]'
            }`}
          >
            Sign Up
          </button>
        </div>

        {/* Form Section */}
        <div className="px-8 pb-8 flex flex-col gap-4">
          {errorMessage && (
            <div className="p-3 rounded-[10px] bg-[#0000000d] border border-[#0000001a] text-[#0d0d0d] text-xs flex items-center gap-2">
              <span className="material-symbols-outlined text-base">error</span>
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {mode === 'register' && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium uppercase tracking-wider text-[#5d5d5d]">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Enter your full name"
                  className="w-full bg-[#ffffff] border border-[#0000001a] rounded-[10px] px-4 py-2.5 text-sm text-[#0d0d0d] placeholder:text-[#8f8f8f] focus:border-[#0d0d0d] outline-none transition-colors"
                />
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium uppercase tracking-wider text-[#5d5d5d]">
                Email address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="w-full bg-[#ffffff] border border-[#0000001a] rounded-[10px] px-4 py-2.5 text-sm text-[#0d0d0d] placeholder:text-[#8f8f8f] focus:border-[#0d0d0d] outline-none transition-colors"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs font-medium uppercase tracking-wider text-[#5d5d5d]">
                  Password
                </label>
                {mode === 'login' && (
                  <a href="#" className="text-xs text-[#0d0d0d] underline hover:text-black">
                    Forgot?
                  </a>
                )}
              </div>
              <input
                type="password"
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full bg-[#ffffff] border border-[#0000001a] rounded-[10px] px-4 py-2.5 text-sm text-[#0d0d0d] placeholder:text-[#8f8f8f] focus:border-[#0d0d0d] outline-none transition-colors"
              />
            </div>

            <div className="mt-2 flex flex-col gap-3">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-[#0d0d0d] hover:bg-[#000000] text-white font-medium py-2.5 rounded-[10px] flex justify-center items-center gap-2 transition-colors text-sm disabled:opacity-50 cursor-pointer"
              >
                {isLoading ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">
                      sync
                    </span>
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>Continue</span>
                    <span className="material-symbols-outlined text-sm">
                      arrow_forward
                    </span>
                  </>
                )}
              </button>

              <button
                type="button"
                onClick={onClose}
                className="w-full bg-transparent border border-[#0000001a] hover:bg-[#0000000d] text-[#0d0d0d] font-medium py-2.5 rounded-[10px] transition-colors text-sm cursor-pointer"
              >
                Continue as Guest
              </button>
            </div>
          </form>

          <div className="mt-3 text-center">
            <p className="text-xs text-[#8f8f8f] leading-[1.43]">
              By continuing, you agree to VietraAI <br />
              <a href="#" className="text-[#0d0d0d] underline hover:text-black transition-colors">
                Terms of Service
              </a>{' '}
              &{' '}
              <a href="#" className="text-[#0d0d0d] underline hover:text-black transition-colors">
                Privacy Policy
              </a>
              .
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
