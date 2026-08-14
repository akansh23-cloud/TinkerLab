export function DemoModelWarning({text}:{text?:string}) {
  if (!text) return null;
  return <div className="notice" data-testid="demo-model-warning"><strong>DEMO MODEL</strong><div className="muted">{text}</div><div className="muted">Do not use this synthetic software-validation fixture for real material decisions.</div></div>;
}
