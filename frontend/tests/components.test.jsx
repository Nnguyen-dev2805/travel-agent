import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import LoginModal from '../src/components/auth/LoginModal';
import ItineraryTimeline from '../src/components/planner/ItineraryTimeline';

describe('LoginModal Component', () => {
  it('renders presets and login buttons', () => {
    render(<LoginModal onLoginSuccess={() => {}} />);
    expect(screen.getByText('Travel Agent AI')).toBeDefined();
    expect(screen.getByText('Alice (Đà Nẵng & Hội An)')).toBeDefined();
    expect(screen.getByText('Bob (Hà Giang Explorer)')).toBeDefined();
    expect(screen.getByPlaceholderText(/Nhập Bearer Token/i)).toBeDefined();
  });

  it('triggers onLoginSuccess when a preset is selected', () => {
    const handleLogin = vi.fn();
    render(<LoginModal onLoginSuccess={handleLogin} />);
    const aliceBtn = screen.getByText('Alice (Đà Nẵng & Hội An)');
    fireEvent.click(aliceBtn);
    expect(handleLogin).toHaveBeenCalledOnce();
  });
});

describe('ItineraryTimeline Component', () => {
  it('renders empty state when no items exist', () => {
    render(<ItineraryTimeline items={[]} />);
    expect(
      screen.getByText(/Chưa có hoạt động nào trong phiên bản lịch trình này/i)
    ).toBeDefined();
  });

  it('renders items grouped by day', () => {
    const items = [
      {
        itinerary_item_id: 'item_1',
        day_index: 1,
        position: 1,
        item_type: 'meal',
        title: 'Ăn mì Quảng Ếch',
        start_time: '08:00',
        location: 'Đà Nẵng',
      },
      {
        itinerary_item_id: 'item_2',
        day_index: 2,
        position: 1,
        item_type: 'activity',
        title: 'Thăm Ngũ Hành Sơn',
        start_time: '09:00',
        location: 'Đà Nẵng',
      },
    ];

    render(<ItineraryTimeline items={items} />);
    expect(screen.getByText('Ngày 1')).toBeDefined();
    expect(screen.getByText('Ngày 2')).toBeDefined();
    expect(screen.getByText('Ăn mì Quảng Ếch')).toBeDefined();
    expect(screen.getByText('Thăm Ngũ Hành Sơn')).toBeDefined();
  });
});
