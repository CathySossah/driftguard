import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  IconDashboard, IconMonitoring, IconAlert, IconModels, IconCompare,
  IconAudit, IconSettings, IconUsers, IconHistory, IconLogout, IconDatasets,
} from './icons'

const adminNav = [
  { to: '/dashboard', label: 'Tableau de bord', icon: IconDashboard },
  { to: '/datasets', label: 'Datasets', icon: IconDatasets },
  { to: '/monitoring', label: 'Monitoring', icon: IconMonitoring },
  { to: '/alerts', label: 'Alertes', icon: IconAlert },
  { to: '/models', label: 'Modèles', icon: IconModels },
  { to: '/compare', label: 'Comparer', icon: IconCompare },
  { to: '/audit', label: 'Journal d\'audit', icon: IconAudit },
  { to: '/settings', label: 'Paramètres', icon: IconSettings },
  { to: '/users', label: 'Utilisateurs', icon: IconUsers },
]

const userNav = [
  { to: '/home', label: 'Accueil', icon: IconDashboard },
  { to: '/predict', label: 'Prédire', icon: IconMonitoring },
  { to: '/history', label: 'Historique', icon: IconHistory },
]

// Sous-ensemble compact pour la barre de navigation mobile (5 max, pour rester lisible).
const adminNavMobile = [adminNav[0], adminNav[1], adminNav[3], adminNav[4], adminNav[8]]

function initials(name = '') {
  return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
}

export default function Layout() {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()
  const nav = isAdmin ? adminNav : userNav
  const mobileNav = isAdmin ? adminNavMobile : userNav

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Drift<span>Guard</span></div>
        <div className="brand-sub">Espace {isAdmin ? 'administrateur' : 'utilisateur'}</div>

        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
          >
            <Icon /> {label}
          </NavLink>
        ))}

        <div className="sidebar-footer">
          <div className="user-chip">
            <div className="avatar">{initials(user?.full_name)}</div>
            <div>
              <div className="name">{user?.full_name}</div>
              <div className="role">{isAdmin ? 'Administrateur' : 'Utilisateur'}</div>
            </div>
          </div>
          <span className="logout" onClick={handleLogout}>Se déconnecter</span>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>

      <nav className="bottom-nav">
        {mobileNav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
          >
            <Icon />
            <span>{label}</span>
          </NavLink>
        ))}
        <button className="nav-item" onClick={handleLogout} style={{ background: 'none', border: 'none' }}>
          <IconLogout />
          <span>Sortir</span>
        </button>
      </nav>
    </div>
  )
}
