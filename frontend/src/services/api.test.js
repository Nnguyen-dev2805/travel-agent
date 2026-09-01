import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { sendChatMessage } from './api'

vi.mock('axios')

describe('sendChatMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('posts the user message to the chat API', async () => {
    axios.post.mockResolvedValueOnce({
      data: {
        reply: 'Xin chao',
        model: 'test-model',
        citations: [],
      },
    })

    const result = await sendChatMessage('Plan a Da Nang trip')

    expect(axios.post).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/chat',
      { message: 'Plan a Da Nang trip' },
    )
    expect(result.reply).toBe('Xin chao')
    expect(result.model).toBe('test-model')
    expect(result.citations).toEqual([])
  })

  it('surfaces backend detail errors', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    axios.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Message content cannot be empty.',
        },
      },
    })

    await expect(sendChatMessage('   ')).rejects.toThrow(
      'Message content cannot be empty.',
    )
    expect(consoleError).toHaveBeenCalledOnce()
    consoleError.mockRestore()
  })
})
