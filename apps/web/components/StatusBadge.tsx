export function StatusBadge({status}:{status:string}) {
  const key = status.toLowerCase();
  const cls = key === "pass" ? "pass" : key === "fail" ? "fail" : key === "unknown" ? "unknown" : "";
  return <span className={`badge ${cls}`}>{status}</span>;
}
