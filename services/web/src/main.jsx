import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const demoSummary = {
  catalog_software: 186,
  installations: 24589,
  matched: 23240,
  unknown: 639,
  critical_risks: 18,
  high_risks: 47,
  medium_risks: 92,
}

const demoRisks = [
  { software: 'WinRAR', computer_id: 'PC-0421', risk: 'prohibited', severity: 'critical', reason: 'ПО запрещено внутренней политикой' },
  { software: 'Java 8', computer_id: 'PC-0187', risk: 'outdated', severity: 'medium', reason: 'Версия устарела, требуется обновление' },
  { software: 'Microsoft Office 2016', computer_id: 'PC-0093', risk: 'license_shortage', severity: 'high', reason: 'Установок больше, чем доступных лицензий' },
  { software: 'unknown_tool.exe', computer_id: 'PC-0732', risk: 'unknown', severity: 'medium', reason: 'ПО не найдено в разрешённом каталоге' },
]

const riskLabels = { critical: 'Критический', high: 'Высокий', medium: 'Средний' }

async function loadData() {
  try {
    const [summaryResponse, risksResponse] = await Promise.all([
      fetch('/api/v1/dashboard/summary'),
      fetch('/api/v1/risks'),
    ])
    if (!summaryResponse.ok || !risksResponse.ok) throw new Error('API unavailable')
    return { summary: await summaryResponse.json(), risks: await risksResponse.json(), live: true }
  } catch {
    return { summary: demoSummary, risks: demoRisks, live: false }
  }
}

function StatCard({ label, value, tone, hint }) {
  return <article className={`stat-card ${tone}`}>
    <div className="stat-top"><span>{label}</span><span className="stat-dot" /></div>
    <strong>{value.toLocaleString('ru-RU')}</strong>
    <small>{hint}</small>
  </article>
}

function App() {
  const [data, setData] = useState({ summary: demoSummary, risks: demoRisks, live: false })
  const [active, setActive] = useState('Обзор')

  useEffect(() => { loadData().then(setData) }, [])

  const { summary, risks } = data
  const matchPercent = summary.installations ? Math.round(summary.matched / summary.installations * 100) : 0

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">S</div><div><b>SAM<span>oparser</span></b><small>Бархатный деплой</small></div></div>
      <div className="workspace"><span className="workspace-icon">⌂</span><div><small>Рабочее пространство</small><b>СургутАСУнефть</b></div><span className="chevron">⌄</span></div>
      <nav className="nav"><p>РАБОЧИЙ СТОЛ</p>{['Обзор', 'Установки', 'Каталог ПО', 'Лицензии'].map((item, index) => <button className={active === item ? 'nav-item active' : 'nav-item'} onClick={() => setActive(item)} key={item}><span>{['◈', '▦', '◉', '◇'][index]}</span>{item}{item === 'Установки' && <em>{summary.installations.toLocaleString('ru-RU')}</em>}</button>)}<p>КОНТРОЛЬ</p><button className="nav-item"><span>⚠</span>Очередь проверки<em className="danger-count">{summary.unknown}</em></button><button className="nav-item"><span>↗</span>Отчёты</button></nav>
      <div className="sidebar-bottom"><div className="sync"><span className="pulse" />Система работает</div><div className="user"><div className="avatar">АД</div><div><b>Алексей Дмитриев</b><small>Администратор</small></div><span>•••</span></div></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div className="crumbs">Рабочий стол <span>/</span> <b>{active}</b></div><div className="top-actions"><button className="icon-button">⌕</button><button className="icon-button notification">♧<i /></button><button className="help-button">?</button></div></header>
      <section className="page-head"><div><div className="eyebrow">ПАНЕЛЬ УПРАВЛЕНИЯ <span className={data.live ? 'live-badge' : 'demo-badge'}>{data.live ? 'LIVE API' : 'DEMO DATA'}</span></div><h1>Обзор активов</h1><p>Контроль программного обеспечения и лицензионных рисков</p></div><button className="primary-button" onClick={() => loadData().then(setData)}><span>↻</span> Обновить данные</button></section>
      <section className="stats-grid"><StatCard label="Всего установок" value={summary.installations} hint="на рабочих станциях" tone="blue" /><StatCard label="В каталоге" value={summary.catalog_software} hint="разрешённых продуктов" tone="violet" /><StatCard label="Сопоставлено" value={matchPercent} hint="процент от всех установок" tone="green" /><StatCard label="Нужно внимания" value={summary.critical_risks + summary.high_risks + summary.medium_risks} hint="активных рисков" tone="orange" /></section>
      <section className="content-grid"><article className="panel chart-panel"><div className="panel-head"><div><h2>Состояние инвентаризации</h2><p>Результаты обработки установленных программ</p></div><button className="dots">•••</button></div><div className="chart-body"><div className="donut" style={{ '--match': `${matchPercent * 3.6}deg` }}><div><strong>{matchPercent}%</strong><span>сопоставлено</span></div></div><div className="legend"><div><i className="legend-green" /><span>Сопоставлено</span><b>{summary.matched.toLocaleString('ru-RU')}</b></div><div><i className="legend-yellow" /><span>На проверке</span><b>{summary.unknown.toLocaleString('ru-RU')}</b></div><div><i className="legend-gray" /><span>Не обработано</span><b>710</b></div></div></div></article><article className="panel risk-overview"><div className="panel-head"><div><h2>Риски по уровню</h2><p>Требуют вашего внимания</p></div><button className="link-button">Подробнее →</button></div><div className="risk-bars"><div className="bar-row"><div><span>Критический</span><b>{summary.critical_risks}</b></div><div className="bar"><i className="bar-critical" style={{ width: `${Math.max(12, summary.critical_risks / 50 * 100)}%` }} /></div></div><div className="bar-row"><div><span>Высокий</span><b>{summary.high_risks}</b></div><div className="bar"><i className="bar-high" style={{ width: `${Math.max(18, summary.high_risks / 50 * 100)}%` }} /></div></div><div className="bar-row"><div><span>Средний</span><b>{summary.medium_risks}</b></div><div className="bar"><i className="bar-medium" style={{ width: `${Math.max(30, summary.medium_risks / 100 * 100)}%` }} /></div></div></div></article></section>
      <section className="panel table-panel"><div className="panel-head"><div><h2>Последние риски</h2><p>Программы, которые требуют проверки</p></div><div className="table-actions"><button className="filter-button">≡ Фильтр</button><button className="link-button">Все риски →</button></div></div><div className="table-wrap"><table><thead><tr><th>ПРОГРАММА</th><th>УСТРОЙСТВО</th><th>ТИП РИСКА</th><th>ОБОСНОВАНИЕ</th><th /></tr></thead><tbody>{risks.slice(0, 5).map((item, index) => <tr key={`${item.software}-${item.computer_id}-${index}`}><td><div className="product-cell"><div className="product-icon">{item.software.slice(0, 1).toUpperCase()}</div><b>{item.software}</b></div></td><td><code>{item.computer_id}</code></td><td><span className={`risk-pill ${item.severity}`}>{riskLabels[item.severity] || item.severity}</span></td><td className="reason">{item.reason}</td><td><button className="row-menu">•••</button></td></tr>)}</tbody></table></div></section>
      <footer><span>Последнее обновление: сегодня, 14:32</span><span><i className="pulse" /> Все системы в норме</span></footer>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
