import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { AuroraBackground } from './components/ui/aurora-background'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuroraBackground />
    <App />
  </React.StrictMode>,
)
