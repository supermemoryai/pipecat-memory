import { createRoot } from "react-dom/client"
import VoiceApp from "./app"

const appElement = document.getElementById("app")
if (!appElement) throw new Error("App element not found")
const root = createRoot(appElement)

root.render(<VoiceApp />)
