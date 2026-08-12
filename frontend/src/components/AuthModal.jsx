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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-[#252b28] border border-[#3d3d3d] shadow-[0px_8px_24px_rgba(0,0,0,0.5)] rounded-xl w-full max-w-[440px] flex flex-col overflow-hidden relative text-white">
        {/* Close Icon */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white p-1 transition-colors rounded-lg hover:bg-white/10"
        >
          <span className="material-symbols-outlined text-xl">close</span>
        </button>

        {/* Header Section */}
        <div className="px-8 pt-10 pb-6 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[#353535] mb-6 border border-[#3d3d3d] shadow-sm">
            <span
              className="material-symbols-outlined text-[#61dbb4] text-3xl"
              style={{ fontVariationSettings: "'FILL' 1" }}
            >
              flight_takeoff
            </span>
          </div>
          <h2 className="text-3xl font-semibold text-white mb-2 tracking-tight">
            VietraAI
          </h2>
          <p className="text-sm text-[#bccac2] leading-relaxed">
            Welcome to VietraAI - Sign in or create an account to start your travel journey
          </p>
        </div>

        {/* Tabs */}
        <div className="px-8 flex border-b border-[#3d3d3d] mb-6">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setErrorMessage('');
            }}
            className={`flex-1 pb-3 text-sm font-medium transition-colors text-center ${
              mode === 'login'
                ? 'text-[#61dbb4] border-b-2 border-[#10a37f]'
                : 'text-[#bccac2] hover:text-white'
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
            className={`flex-1 pb-3 text-sm font-medium transition-colors text-center ${
              mode === 'register'
                ? 'text-[#61dbb4] border-b-2 border-[#10a37f]'
                : 'text-[#bccac2] hover:text-white'
            }`}
          >
            Sign Up
          </button>
        </div>

        {/* Form Section */}
        <div className="px-8 pb-8 flex flex-col gap-4">
          {errorMessage && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center gap-2">
              <span className="material-symbols-outlined text-base">error</span>
              <span>{errorMessage}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {mode === 'register' && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium uppercase tracking-wider text-[#bccac2]">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Enter your full name"
                  className="w-full bg-[#171717] border border-[#3d3d3d] rounded-lg px-4 py-3 text-sm text-white placeholder:text-[#86948d] focus:border-[#61dbb4] outline-none transition-colors"
                />
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium uppercase tracking-wider text-[#bccac2]">
                Email address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="w-full bg-[#171717] border border-[#3d3d3d] rounded-lg px-4 py-3 text-sm text-white placeholder:text-[#86948d] focus:border-[#61dbb4] outline-none transition-colors"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between items-center">
                <label className="text-xs font-medium uppercase tracking-wider text-[#bccac2]">
                  Password
                </label>
                {mode === 'login' && (
                  <a href="#" className="text-xs text-[#61dbb4] hover:underline">
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
                className="w-full bg-[#171717] border border-[#3d3d3d] rounded-lg px-4 py-3 text-sm text-white placeholder:text-[#86948d] focus:border-[#61dbb4] outline-none transition-colors"
              />
            </div>

            <div className="mt-2 flex flex-col gap-3">
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-[#10a37f] hover:bg-[#0e8f6e] text-white font-medium py-3 rounded-lg flex justify-center items-center gap-2 transition-colors text-sm shadow-md disabled:opacity-50 cursor-pointer"
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
                className="w-full bg-transparent border border-[#3d3d3d] hover:bg-white/5 text-white font-medium py-3 rounded-lg transition-colors text-sm cursor-pointer"
              >
                Continue as Guest
              </button>
            </div>
          </form>

          <div className="mt-4 text-center">
            <p className="text-xs text-[#bccac2] leading-relaxed">
              By continuing, you agree to VietraAI <br />
              <a href="#" className="text-white hover:text-[#61dbb4] underline transition-colors">
                Terms of Service
              </a>{' '}
              &{' '}
              <a href="#" className="text-white hover:text-[#61dbb4] underline transition-colors">
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
