import "./globals.css";
import Providers from "@/components/Providers";
import { Shell } from "@/components/Shell";
export const metadata = { title: "TinkerLab", description: "Material Replacement OS — Phase 12.2.2" };
export default function RootLayout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body><Providers><Shell>{children}</Shell></Providers></body></html>;
}
