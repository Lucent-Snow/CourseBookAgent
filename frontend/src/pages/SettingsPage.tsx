import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Bot, CheckCircle2, Database, GraduationCap, HardDrive, Plug, Save, Settings2, Sparkles } from 'lucide-react'
import { api } from '@/api/client'
import { productApi } from '@/api/product'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ProviderAuthStatus } from '@/product-types'
import type { Settings } from '@/types'

function Section({ icon, title, description, children }: { icon: ReactNode; title: string; description: string; children: ReactNode }) {
  return <section className="rounded-lg border border-[#dfe6e6] bg-white"><header className="flex items-start gap-3 border-b border-[#edf0f0] px-5 py-4"><span className="grid size-9 place-items-center rounded-md bg-[#e8f3f3] text-[#147d86]">{icon}</span><div><h2 className="text-sm font-semibold">{title}</h2><p className="mt-1 text-xs text-[#718183]">{description}</p></div></header><div className="p-5">{children}</div></section>
}

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [webvpn, setWebvpn] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [providers, setProviders] = useState<ProviderAuthStatus | null>(null)

  function refresh() {
    void productApi.providerAuth().then(setProviders).catch((err) => setError((err as Error).message))
  }

  useEffect(() => {
    void api.settings().then((value) => { setSettings(value); setBaseUrl(value.llm.base_url); setModel(value.llm.model) }).catch((err) => setError((err as Error).message))
    refresh()
  }, [])
  async function execute(action: () => Promise<void>) { setBusy(true); setError(''); setMessage(''); try { await action() } catch (err) { setError((err as Error).message) } finally { setBusy(false) } }
  async function saveLlm() { await execute(async () => { const result = await api.saveLlm(baseUrl, model, apiKey); setBaseUrl(result.base_url); setApiKey(''); setSettings((current) => current ? { ...current, llm: { ...current.llm, base_url: result.base_url, model, configured: result.configured, api_key_set: result.api_key_set } } : current); setMessage('模型配置已保存'); refresh() }) }
  async function login(event: FormEvent) {
    event.preventDefault()
    await execute(async () => {
      const response = await productApi.unifiedLogin(username, password, webvpn)
      setPassword('')
      setProviders(response.providers)
      const summary = (response.warnings && response.warnings.length) ? `登录部分成功：${response.warnings.join('；')}` : `智云课堂与学在浙大已连接（${response.username}）`
      setMessage(summary)
      refresh()
    })
  }
  const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return <div className="mx-auto max-w-[1080px] px-4 py-6 md:px-10 md:py-10"><header><p className="text-xs font-semibold text-[#147d86]">SYSTEM SETTINGS</p><h1 className="mt-2 text-[28px] font-semibold">系统设置</h1><p className="mt-2 text-sm text-[#718183]">配置数据源、模型和本地存储。运行创建后不会被这里的修改追溯覆盖。</p></header>{message && <div className="mt-5 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"><CheckCircle2 size={16} />{message}</div>}{error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}<div className="mt-7 grid gap-5">
    <Section icon={<Plug size={17} />} title="统一身份认证" description="一次登录同时连接智云课堂和学在浙大"><form onSubmit={login} className="grid grid-cols-1 items-end gap-3 md:grid-cols-[1fr_1fr_auto]"><label className="text-xs text-[#657678]">学号<Input className="mt-2" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label><label className="text-xs text-[#657678]">密码<Input className="mt-2" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label><Button type="submit" disabled={busy}>{providers?.zhiyun.authenticated || providers?.xue_zai_zju.authenticated ? '重新连接' : '连接账号'}</Button></form><label className="mt-4 flex items-center gap-2 text-xs text-[#718183]"><input type="checkbox" checked={webvpn} onChange={(e) => setWebvpn(e.target.checked)} />校外网络使用 WebVPN</label><div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2"><div className="rounded-md bg-[#f7f9f9] p-3"><p className="text-[10px] font-semibold uppercase text-[#718183]">智云课堂</p><p className="mt-1 text-sm font-medium">{providers?.zhiyun.authenticated ? `已连接 ${providers.zhiyun.username}` : '未连接'}</p></div><div className="rounded-md bg-[#f7f9f9] p-3"><p className="text-[10px] font-semibold uppercase text-[#718183]">学在浙大</p><p className="mt-1 text-sm font-medium">{providers?.xue_zai_zju.authenticated ? `已连接 ${providers.xue_zai_zju.username}` : '未连接'}</p></div></div><p className="mt-3 text-[11px] text-[#879496]">智云和学在浙大分别使用独立的会话；任何一方失败不会阻塞另一方。</p></Section>
    <Section icon={<Sparkles size={17} />} title="课程资料导入" description="每个资料集都可以从平台独立导入，无需反复登录"><p className="text-xs text-[#718183]">在任意资料集的“从平台导入”入口中，按指引选择智云课堂或学在浙大，再选择课程与资料。</p><div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2"><div className="rounded-md bg-[#f7f9f9] p-3"><p className="text-[11px] font-medium flex items-center gap-1.5"><Bot size={13} className="text-[#147d86]" />智云课堂</p><p className="mt-1 text-[11px] text-[#718183]">讲次字幕、智云课件页（PPT 时间轴）</p></div><div className="rounded-md bg-[#f7f9f9] p-3"><p className="text-[11px] font-medium flex items-center gap-1.5"><GraduationCap size={13} className="text-[#147d86]" />学在浙大</p><p className="mt-1 text-[11px] text-[#718183]">原始 PDF / PPTX / DOCX 课件，按文件名与模块分组</p></div></div></Section>
    <Section icon={<Bot size={17} />} title="模型与 Agent" description="配置 OpenAI 兼容模型；工作流在每次运行中选择并发与审校策略"><div className="grid grid-cols-2 gap-4"><label className="text-xs text-[#657678]">API 端点<Input className="mt-2" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" /></label><label className="text-xs text-[#657678]">模型名<Input className="mt-2" value={model} onChange={(e) => setModel(e.target.value)} placeholder="qwen-plus" /></label></div><label className="mt-4 block text-xs text-[#657678]">API Key<Input className="mt-2" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={settings?.llm.api_key_set ? '已设置；留空表示不修改' : 'sk-...'} /></label><div className="mt-4 flex gap-2"><Button disabled={busy} onClick={() => void saveLlm()}><Save size={14} />保存模型配置</Button><Button variant="outline" disabled={busy || !settings?.llm.configured} onClick={() => void execute(async () => { const result = await api.testLlm(); setMessage(`连接成功：${result.model} · ${result.latency_ms} ms`) })}>测试连接</Button></div></Section>
    <div className="grid gap-5 lg:grid-cols-2"><Section icon={<Settings2 size={17} />} title="运行默认值" description="当前内置课程教辅工作流的默认策略"><dl className="space-y-3 text-xs">{[['最大并行章节 Agent','3'],['失败自动重试','2 次'],['运行超时','60 分钟'],['中间产物预览','开启']].map(([key,value]) => <div key={key} className="flex justify-between rounded-md bg-[#f7f9f9] px-3 py-2.5"><dt className="text-[#718183]">{key}</dt><dd className="font-medium">{value}</dd></div>)}</dl><p className="mt-3 text-[10px] leading-4 text-[#879496]">这些是当前后端策略摘要；并发和语义审校可在创建运行时覆盖。</p></Section><Section icon={<HardDrive size={17} />} title="存储与缓存" description="资料原文件、解析文本、输入快照和运行检查点保存在本机"><div className="flex items-center justify-between rounded-md bg-[#f7f9f9] p-3"><span className="flex items-center gap-2 text-xs text-[#657678]"><Database size={14} />当前数据占用</span><strong className="text-sm">{settings ? mb(settings.data.cache_bytes) : '—'}</strong></div><p className="mt-3 text-[11px] leading-5 text-[#879496]">清理派生产物会保留原始字幕、蓝图、任务快照和质量记录；资料集上传文件也不会被清除。</p><Button variant="outline" className="mt-4" disabled={busy} onClick={() => { if (window.confirm('确定清除可重新生成的中间产物与输出？')) void execute(async () => { const result = await api.clearCache(); setMessage(`已清理：${result.removed.join('、') || '无可清理内容'}`) }) }}>清理派生缓存</Button></Section></div>
  </div></div>
}
