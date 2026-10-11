import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DemoApp from './demo/DemoApp'

async function mount() {
  // Establish the guest cookie before parallel workspace API requests.
  try {
    const response = await fetch('/api/session', { credentials: 'same-origin' })
    if (!response.ok) throw new Error('连接失败')
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        {import.meta.env.VITE_DEMO_MODE === 'true' ? <DemoApp /> : <App />}
      </StrictMode>,
    )
  } catch {
    createRoot(document.getElementById('root')!).render(
      <main style={{ padding: '3rem', textAlign: 'center' }}>
        <h1>暂时无法连接工作台</h1>
        <p>请稍后重试，你已保存的资料不会因本次连接失败而丢失。</p>
        <button onClick={() => window.location.reload()}>重新连接</button>
      </main>,
    )
  }
}

void mount()
