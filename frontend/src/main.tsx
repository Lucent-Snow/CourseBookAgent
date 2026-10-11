import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import DemoApp from './demo/DemoApp'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {import.meta.env.VITE_DEMO_MODE === 'true' ? <DemoApp /> : <App />}
  </StrictMode>,
)
