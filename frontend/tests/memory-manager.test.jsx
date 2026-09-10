import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MemoryManager from '../src/components/memory/MemoryManager';
import {
  listMemories,
  sendMemoryCommand,
  createDeletion,
  requestScopeExpansion,
  confirmPreview,
} from '../src/services/memory';

vi.mock('../src/services/memory', () => ({
  listMemories: vi.fn(),
  sendMemoryCommand: vi.fn(),
  createDeletion: vi.fn(),
  requestScopeExpansion: vi.fn(),
  confirmPreview: vi.fn(),
}));

const SEED = [
  {
    version_id: 'mem_first',
    canonical_key: 'travel.preference.hotel_atmosphere',
    normalized_value: 'quiet',
    scope: 'user',
    authority: 'explicit_save',
    sensitivity: 'ordinary_personal',
    valid_from: '2026-09-07T12:00:00+00:00',
  },
  {
    version_id: 'mem_second',
    canonical_key: 'travel.preference.hotel_atmosphere',
    normalized_value: 'lively',
    scope: 'conversation',
    authority: 'explicit_save',
    sensitivity: 'ordinary_personal',
    valid_from: '2026-09-07T13:00:00+00:00',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  listMemories.mockResolvedValue(SEED);
});

describe('MemoryManager', () => {
  it('shows a loading state, then inspects governed fields', async () => {
    render(<MemoryManager onClose={() => {}} />);
    expect(screen.getByText(/loading memories/i)).toBeDefined();
    expect(await screen.findByText('quiet')).toBeDefined();
    expect(screen.getByText('lively')).toBeDefined();
    expect(screen.getAllByText('travel.preference.hotel_atmosphere')).toHaveLength(2);
  });

  it('shows an empty state when no memories exist', async () => {
    listMemories.mockResolvedValue([]);
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText(/no saved memories/i)).toBeDefined();
  });

  it('shows an error state with retry that reloads the list', async () => {
    listMemories.mockRejectedValueOnce(new Error('boom'));
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText(/could not load memories/i)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('quiet')).toBeDefined();
    expect(listMemories).toHaveBeenCalledTimes(2);
  });

  it('saves directly with no confirmation step', async () => {
    sendMemoryCommand.mockResolvedValue({
      status: 'saved',
      operation: 'add',
      scope: 'user',
      canonical_key: 'travel.preference.hotel_atmosphere',
      normalized_value: 'quiet',
      version_id: 'mem_new',
    });
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('quiet')).toBeDefined();

    fireEvent.change(screen.getByLabelText(/memory command/i), {
      target: { value: 'remember quiet hotels' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(await screen.findByText(/saved/i)).toBeDefined();
    expect(screen.queryByText(/confirm/i)).toBeNull();
  });

  it('renders refusals without prompting', async () => {
    sendMemoryCommand.mockResolvedValue({
      status: 'refused',
      reason_code: 'prohibited_content',
    });
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('quiet')).toBeDefined();

    fireEvent.change(screen.getByLabelText(/memory command/i), {
      target: { value: 'remember api key sk-test-x' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    expect(await screen.findByText(/not saved/i)).toBeDefined();
  });

  it('confirms bulk previews and reports stale conflicts', async () => {
    sendMemoryCommand.mockResolvedValue({
      status: 'preview_required',
      preview: {
        preview_id: 'mprev_1',
        token: 'tok_1',
        operation: 'bulk_delete',
        targets: SEED.map((item) => ({
          version_id: item.version_id,
          canonical_key: item.canonical_key,
          normalized_value: item.normalized_value,
          scope: item.scope,
        })),
        expires_in_seconds: 600,
      },
    });
    const stale = new Error('Memory changed; please review again.');
    stale.status = 409;
    confirmPreview.mockRejectedValueOnce(stale).mockResolvedValueOnce({
      status: 'committed',
      operation: 'bulk_delete',
      committed_version_ids: ['mem_first', 'mem_second'],
      undo: { action: 'restore', version_ids: ['mem_first', 'mem_second'], note: '' },
    });
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('quiet')).toBeDefined();

    fireEvent.change(screen.getByLabelText(/memory command/i), {
      target: { value: 'delete everything' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/review this delete/i)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /^confirm$/i }));
    expect(await screen.findByText(/changed/i)).toBeDefined();
  });

  it('deletes one entry directly with undo feedback', async () => {
    createDeletion.mockResolvedValue({
      status: 'deleted',
      committed_version_ids: ['mem_first'],
      undo: { action: 'restore', version_ids: ['mem_first'], note: '' },
    });
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('quiet')).toBeDefined();

    const deleteButtons = screen.getAllByRole('button', { name: /delete/i });
    fireEvent.click(deleteButtons[0]);
    expect(await screen.findByText(/deleted/i)).toBeDefined();
    expect(createDeletion).toHaveBeenCalledWith({ version_ids: ['mem_first'] });
  });

  it('closes on Escape and focuses the heading on mount', async () => {
    const onClose = vi.fn();
    render(<MemoryManager onClose={onClose} />);
    expect(await screen.findByText('quiet')).toBeDefined();
    expect(document.activeElement?.getAttribute('data-testid')).toBe(
      'memory-manager-heading'
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('cancels preview on Escape before closing the manager', async () => {
    const onClose = vi.fn();
    sendMemoryCommand.mockResolvedValue({
      status: 'preview_required',
      preview: {
        preview_id: 'mprev_esc',
        token: 'tok_esc',
        operation: 'bulk_delete',
        targets: [SEED[0]],
        expires_in_seconds: 600,
      },
    });
    render(<MemoryManager onClose={onClose} />);
    expect(await screen.findByText('quiet')).toBeDefined();

    fireEvent.change(screen.getByLabelText(/memory command/i), {
      target: { value: 'delete' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByText(/review this delete/i)).toBeDefined();

    // First Escape dismisses the preview dialog
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByText(/review this delete/i)).toBeNull();
    expect(onClose).not.toHaveBeenCalled();

    // Second Escape closes the manager drawer
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('refreshes the list on demand', async () => {
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('quiet')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
    await waitFor(() => expect(listMemories).toHaveBeenCalledTimes(2));
  });

  it('requests scope expansion previews for conversation entries', async () => {
    requestScopeExpansion.mockResolvedValue({
      status: 'preview_required',
      preview: {
        preview_id: 'mprev_2',
        token: 'tok_2',
        operation: 'scope_expansion',
        targets: [
          {
            version_id: 'mem_second',
            canonical_key: 'travel.preference.hotel_atmosphere',
            normalized_value: 'lively',
            scope: 'conversation',
          },
        ],
        expires_in_seconds: 600,
      },
    });
    render(<MemoryManager onClose={() => {}} />);
    expect(await screen.findByText('lively')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: /expand/i }));
    expect(
      await screen.findByRole('heading', { name: /widen memory scope/i })
    ).toBeDefined();
    expect(requestScopeExpansion).toHaveBeenCalledWith({
      version_id: 'mem_second',
    });
  });
});
