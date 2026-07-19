import { useState, useRef } from 'react'
import axios from 'axios'

export default function AssistantPanel() {
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<any>(null)

  const askAssistant = async (text: string) => {
    if (!text.trim()) return
    setLoading(true)
    setAnswer('')
    try {
      const res = await axios.post('http://localhost:8000/assistant/query', {
        text,
        officer_id: 'field_officer_1', // swap for real officer login id when auth exists
      })
      setAnswer(res.data.answer)
      speak(res.data.answer)
    } catch (err: any) {
      setAnswer('Error reaching assistant: ' + (err?.message ?? 'unknown error'))
    } finally {
      setLoading(false)
    }
  }

  const speak = (text: string) => {
    if (!('speechSynthesis' in window)) return
    const utterance = new SpeechSynthesisUtterance(text)
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utterance)
  }

  const startListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Speech recognition not supported in this browser — try Chrome.')
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = 'en-IN'
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    recognition.onstart = () => setListening(true)
    recognition.onend = () => setListening(false)
    recognition.onerror = () => setListening(false)
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript
      setQuery(transcript)
      askAssistant(transcript)
    }

    recognitionRef.current = recognition
    recognition.start()
  }

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e2e8f0',
      borderRadius: '8px',
      padding: '16px',
      marginTop: '12px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: '8px', color: '#374151' }}>
        AI Assistant
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && askAssistant(query)}
          placeholder="Ask about a zone, e.g. 'Why is this zone high risk?'"
          style={{
            flex: 1,
            padding: '8px 10px',
            border: '1px solid #cbd5e1',
            borderRadius: '6px',
            fontSize: '14px',
          }}
        />
        <button
          onClick={startListening}
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            border: 'none',
            background: listening ? '#dc2626' : '#2563eb',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          {listening ? '● Listening' : '🎤'}
        </button>
        <button
          onClick={() => askAssistant(query)}
          disabled={loading}
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            border: 'none',
            background: '#16a34a',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          {loading ? '...' : 'Ask'}
        </button>
      </div>

      {answer && (
        <div style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '6px',
          padding: '10px',
          fontSize: '14px',
          color: '#334155',
          whiteSpace: 'pre-wrap',
        }}>
          {answer}
        </div>
      )}
    </div>
  )
}