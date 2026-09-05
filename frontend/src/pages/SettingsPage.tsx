import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/api/client'
import type { Settings } from '@/types'

function Card({ title, badge, children }: { title: string; badge?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-5 py-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        {badge}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [webvpn, setWebvpn] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void api
      .settings()
      .then((s) => {
        setSettings(s)
        setBaseUrl(s.llm.base_url)
        setModel(s.llm.model)
      })
      .catch((err) => setError((err as Error).message))
  }, [])

  function run(action: () => Promise<void>) {
    setBusy(true)
    setError('')
    setStatus('')
    void action()
      .catch((err) => setError((err as Error).message))
      .finally(() => setBusy(false))
  }

  async function saveLlm() {
    await run(async () => {
      const res = await api.saveLlm(baseUrl, model, apiKey)
      setStatus('大模型配置已保存')
      setSettings((s) => (s ? { ...s, llm: { ...s.llm, base_url: baseUrl, model, configured: res.configured } } : s))
    })
  }

  async function testLlm() {
    await run(async () => {
      const res = await api.testLlm()
      setStatus(`连接成功：${res.model}，${res.latency_ms}ms`)
    })
  }

  async function login(e: FormEvent) {
    e.preventDefault()
    await run(async () => {
      const auth = await api.login(username, password, webvpn)
      setPassword('')
      setStatus(`已登录：${auth.username}`)
      setSettings((s) => (s ? { ...s, zhiyun: auth } : s))
    })
  }

  async function clearCache() {
    if (!window.confirm('确定清除中间产物与输出？原始字幕、蓝图、任务快照与质量记录会保留。')) return
    await run(async () => {
      const res = await api.clearCache()
      setStatus(`已清除：${res.removed.join('、')}`)
    })
  }

  const mb = (s: number) => (s / 1024 / 1024).toFixed(1) + ' MB'

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold">设置</h2>
        <p className="mt-1 text-sm text-muted-foreground">配置模型与数据源，首次使用需要完成这两项。</p>
      </div>

      {status && (
        <div className="rounded-md border-l-4 border-emerald-500 bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
          {status}
        </div>
      )}
      {error && (
        <div className="rounded-md border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      )}

      <Card
        title="大模型配置"
        badge={
          settings?.llm.configured ? (
            <Badge className="border-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
              已配置
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-muted-foreground">
              未配置
            </Badge>
          )
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground" htmlFor="base-url">
              API 端点
            </label>
            <Input id="base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://your-host/v1" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground" htmlFor="model">
              模型名
            </label>
            <Input id="model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="qwen-plus" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground" htmlFor="api-key">
              API Key（留空表示不修改）
            </label>
            <Input id="api-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={settings?.llm.api_key_set ? '已设置，留空保持' : 'sk-...'} />
          </div>
          <div className="flex gap-2">
            <Button onClick={saveLlm} disabled={busy}>
              保存配置
            </Button>
            <Button onClick={testLlm} disabled={busy || !settings?.llm.configured} variant="outline">
              测试连接
            </Button>
          </div>
        </div>
      </Card>

      <Card
        title="智云课堂账号"
        badge={
          settings?.zhiyun.authenticated ? (
            <Badge className="border-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
              已登录：{settings.zhiyun.username}
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-muted-foreground">
              未登录
            </Badge>
          )
        }
      >
        <form onSubmit={login} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground" htmlFor="username">
              学号
            </label>
            <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" placeholder="学号" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground" htmlFor="password">
              密码
            </label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="密码" />
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={webvpn} onChange={(e) => setWebvpn(e.target.checked)} className="size-3.5" />
            校外网络，使用 WebVPN
          </label>
          <Button type="submit" disabled={busy}>
            {settings?.zhiyun.authenticated ? '重新登录' : '登录'}
          </Button>
          <p className="text-xs text-muted-foreground">密码仅用于本次认证，不写入本项目。</p>
        </form>
      </Card>

      <Card title="数据与缓存">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            本地数据 {settings ? mb(settings.data.cache_bytes) : '…'} · {settings?.data.course_count ?? 0} 本成书
          </span>
          <Button onClick={clearCache} disabled={busy} variant="outline" size="sm">
            清除缓存
          </Button>
        </div>
      </Card>
    </div>
  )
}
