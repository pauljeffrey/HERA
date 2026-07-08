import AuditTrailView from "@/components/patients/AuditTrailView";

export default async function AuditTrailPage({ params }: { params: Promise<{ patient_id: string }> }) {
  const { patient_id } = await params;
  return <AuditTrailView patientId={patient_id.toUpperCase()} />;
}
