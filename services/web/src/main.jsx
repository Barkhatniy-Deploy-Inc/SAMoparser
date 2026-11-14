import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

function App() {
  return <main><h1>SAMoparser</h1><p>Web scaffold</p></main>
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
