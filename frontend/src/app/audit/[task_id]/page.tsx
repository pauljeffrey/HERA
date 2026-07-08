import AuditDashboard from "@/components/audit/AuditDashboard";

export default async function AuditPage({ params }: { params: Promise<{ task_id: string }> }) {
  const { task_id } = await params;
  return <AuditDashboard taskId={task_id} />;
}
