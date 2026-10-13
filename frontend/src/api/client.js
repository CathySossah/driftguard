import axios from 'axios'

// En développement, l'API tourne sur localhost:8000 (uvicorn).
// En production, définir VITE_API_URL au build (ex. via un fichier .env).
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

if (import.meta.env.PROD && !import.meta.env.VITE_API_URL) {
  console.error('VITE_API_URL n\'est pas défini : le frontend appelle http://localhost:8000. Définissez-la avant le build.')
}

const api = axios.create({
  baseURL: API_BASE_URL,
})

// Ajoute automatiquement le token JWT à chaque requête, s'il est présent.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('driftguard_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Si le serveur répond 401 (session expirée / token invalide), on déconnecte
// proprement l'utilisateur plutôt que de laisser l'app dans un état incohérent.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('driftguard_token')
      localStorage.removeItem('driftguard_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
