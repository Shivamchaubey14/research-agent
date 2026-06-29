export default function StatusBadge({ status }) {
  if (!status) return null;
  return <span className={`badge ${status}`}>{status.toLowerCase()}</span>;
}
