import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Overview } from "./pages/Overview";
import { Incident } from "./pages/Incident";
import { Topology } from "./pages/Topology";
import { Approval } from "./pages/Approval";
import { Risk } from "./pages/Risk";
import { Cost } from "./pages/Cost";
import { Savings } from "./pages/Savings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="incidents/:id" element={<Incident />} />
        <Route path="incidents" element={<Navigate to="/incidents/INC-0042" replace />} />
        <Route path="topology" element={<Topology />} />
        <Route path="approvals/:id" element={<Approval />} />
        <Route path="approvals" element={<Navigate to="/approvals/APR-1182" replace />} />
        <Route path="risk" element={<Risk />} />
        <Route path="cost" element={<Cost />} />
        <Route path="savings" element={<Savings />} />
      </Route>
    </Routes>
  );
}
