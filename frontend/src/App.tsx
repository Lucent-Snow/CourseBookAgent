import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ArtifactDetailPage } from '@/pages/ArtifactDetailPage'
import { ArtifactsPage } from '@/pages/ArtifactsPage'
import { DatasetDetailPage } from '@/pages/DatasetDetailPage'
import { DatasetsPage } from '@/pages/DatasetsPage'
import { ReaderPage } from '@/pages/ReaderPage'
import { ReviewPage } from '@/pages/ReviewPage'
import { RunDetailPage } from '@/pages/RunDetailPage'
import { RunsPage } from '@/pages/RunsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { WorkflowConfigPage } from '@/pages/WorkflowConfigPage'
import { WorkspacePage } from '@/pages/WorkspacePage'

function App() {
  return <BrowserRouter><Routes><Route element={<AppShell />}><Route index element={<Navigate to="/datasets" replace />} /><Route path="/datasets" element={<DatasetsPage />} /><Route path="/datasets/:datasetId" element={<DatasetDetailPage />} /><Route path="/datasets/:datasetId/configure" element={<WorkflowConfigPage />} /><Route path="/runs" element={<RunsPage />} /><Route path="/runs/:runId" element={<RunDetailPage />} /><Route path="/artifacts" element={<ArtifactsPage />} /><Route path="/artifacts/:artifactId" element={<ArtifactDetailPage />} /><Route path="/settings" element={<SettingsPage />} /><Route path="/workspace" element={<WorkspacePage />} /><Route path="/read/:courseId" element={<ReaderPage />} /><Route path="/review" element={<ReviewPage />} /></Route></Routes></BrowserRouter>
}
export default App
