import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ShelfPage } from '@/pages/ShelfPage'
import { WorkspacePage } from '@/pages/WorkspacePage'
import { ReaderPage } from '@/pages/ReaderPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { ReviewPage } from '@/pages/ReviewPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<ShelfPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/read/:courseId" element={<ReaderPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/review" element={<ReviewPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
