"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";

const icons:Record<string,string>={
  dashboard:"M4 13h6V4H4v9Zm10 7h6V11h-6v9ZM4 20h6v-5H4v5Zm10-11h6V4h-6v5Z",
  materials:"M12 3 4 7v10l8 4 8-4V7l-8-4Zm0 2.2L17.6 8 12 10.8 6.4 8 12 5.2ZM6 10l5 2.5v5.9l-5-2.5V10Zm7 8.4v-5.9l5-2.5v5.9l-5-2.5Z",
  discover:"M11 2a9 9 0 1 0 5.65 16L22 23.35 23.35 22 18 16.65A9 9 0 0 0 11 2Zm0 2a7 7 0 1 1 0 14 7 7 0 0 1 0-14Zm3.8 3.2-5.2 2.4-2.4 5.2 5.2-2.4 2.4-5.2Zm-3.1 3.1-.6 1.3-1.3.6.6-1.3 1.3-.6Z",
  requirements:"M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm2 5h8V6H8v2Zm0 5h8v-2H8v2Zm0 5h5v-2H8v2Z",
  lab:"M9 3h6v2h-1v4.1l4.7 7.9A2.7 2.7 0 0 1 16.4 21H7.6a2.7 2.7 0 0 1-2.3-4L10 9.1V5H9V3Zm2.8 7-4.7 8a.7.7 0 0 0 .5 1h8.8a.7.7 0 0 0 .5-1l-4.7-8h-.4Z",
  evidence:"M5 4h14v16H5V4Zm3 4h8V6H8v2Zm0 4h8v-2H8v2Zm0 4h6v-2H8v2Z",
  decisions:"M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm4.6 7.4-5.3 6a1 1 0 0 1-1.5.1l-2.4-2.4 1.4-1.4 1.7 1.7 4.6-5.2 1.5 1.2Z",
  reports:"M6 2h9l4 4v16H6V2Zm8 2v3h3l-3-3ZM9 11h6V9H9v2Zm0 4h6v-2H9v2Zm0 4h4v-2H9v2Z",
  settings:"M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm9 3.5-2.1-.8a7 7 0 0 0-.5-1.2l.9-2-2.3-2.3-2 .9a7 7 0 0 0-1.2-.5L13 4h-2l-.8 2.1a7 7 0 0 0-1.2.5l-2-.9L4.7 8l.9 2a7 7 0 0 0-.5 1.2L3 12v2l2.1.8c.1.4.3.8.5 1.2l-.9 2L7 20.3l2-.9c.4.2.8.4 1.2.5L11 22h2l.8-2.1c.4-.1.8-.3 1.2-.5l2 .9 2.3-2.3-.9-2c.2-.4.4-.8.5-1.2L21 14v-2Z",
};
function NavIcon({name}:{name:string}){return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={icons[name]}/></svg>}
const nav=[
  {label:"Dashboard",href:"/",icon:"dashboard",match:(p:string)=>p==="/"},
  {label:"Materials",href:"/materials",icon:"materials",match:(p:string)=>p.startsWith("/materials")||p.startsWith("/explore")||p.startsWith("/imports")||p.startsWith("/data-sources")},
  {label:"Discover",href:"/discover",icon:"discover",match:(p:string)=>p.startsWith("/discover")},
  {label:"Requirements",href:"/requirements",icon:"requirements",match:(p:string)=>p.startsWith("/requirements")||p.startsWith("/studies")},
  {label:"Virtual Lab",href:"/virtual-lab",icon:"lab",match:(p:string)=>p.includes("virtual-lab")||p.startsWith("/virtual-campaigns")},
  {label:"Validation Plan",href:"/validation-plan",icon:"lab",match:(p:string)=>p.startsWith("/validation-plan")},
  {label:"Evidence",href:"/evidence",icon:"evidence",match:(p:string)=>p.startsWith("/evidence")||p==="/validation"||p.startsWith("/validation/")||p.startsWith("/observations")},
  {label:"Decisions",href:"/decisions",icon:"decisions",match:(p:string)=>p.startsWith("/decisions")||p.startsWith("/reasoning")||p.includes("/replacement")},
  {label:"Reports",href:"/reports",icon:"reports",match:(p:string)=>p.startsWith("/reports")},
  {label:"Settings",href:"/settings",icon:"settings",match:(p:string)=>p.startsWith("/settings")||p.startsWith("/data-sources")},
];
export function Shell({children}:{children:React.ReactNode}){
  const pathname=usePathname();
  return <div className="shell tinker-shell">
    <aside className="sidebar tinker-sidebar">
      <Link href="/" className="brand-lockup"><span className="brand-mark"><span/></span><span><strong>TinkerLab</strong><small>Material Decision OS</small></span></Link>
      <nav className="nav tinker-nav">{nav.map(item=><Link key={item.label} href={item.href} className={item.match(pathname)?"active":""}><NavIcon name={item.icon}/><span>{item.label}</span></Link>)}</nav>
      <div className="sidebar-spacer"/>
      <div className="workspace-switcher"><span className="workspace-label">Workspace</span><strong>Power Electronics Lab</strong><span className="workspace-meta"><i/> Scientific workspace</span></div>
      <div className="sidebar-profile"><span className="avatar">TL</span><span><strong>Demo Workspace</strong><small>Evidence-first mode</small></span></div>
      <div className="sidebar-footline">Deterministic decisions · no generative AI</div>
    </aside>
    <main className="main tinker-main">
      <header className="app-topbar"><div className="topbar-context"><span className="context-orbit"/><span>Scientific decision workspace</span></div><div className="topbar-tools"><label className="global-search"><svg viewBox="0 0 24 24"><path d="M10.5 4a6.5 6.5 0 1 0 4.1 11.55L20 21l1-1-5.45-5.4A6.5 6.5 0 0 0 10.5 4Zm0 2a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9Z"/></svg><input aria-label="Search" placeholder="Search materials, studies, evidence…"/></label><span className="system-pill"><i/> System ready</span></div></header>
      <div className="page-canvas">{children}</div>
    </main>
  </div>;
}
