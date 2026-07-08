import PatientChartRoom from "@/components/patients/PatientChartRoom";

export default async function PatientPage({ params }: { params: Promise<{ patient_id: string }> }) {
  const { patient_id } = await params;
  return <PatientChartRoom patientId={patient_id.toUpperCase()} />;
}
