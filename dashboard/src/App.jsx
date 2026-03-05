import { useState } from 'react'
import NavBar from './components/NavBar'
import StatusDashboard from './components/StatusDashboard'
import SearchPanel from './components/SearchPanel'
import VaultExplorer from './components/VaultExplorer'
import AgentMonitor from './components/AgentMonitor'
import SettingsPanel from './components/SettingsPanel'

const VIEWS = {
  dashboard: StatusDashboard,
  search: SearchPanel,
  vault: VaultExplorer,
  agents: AgentMonitor,
  settings: SettingsPanel,
}

export default function App() {
  const [view, setView] = useState('dashboard')
  const View = VIEWS[view]

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <NavBar active={view} onNavigate={setView} />
      <main style={{
        flex: 1,
        overflow: 'auto',
        padding: '28px 32px',
        background: '#080c14',
      }}>
        <View />
      </main>
    </div>
  )
}
