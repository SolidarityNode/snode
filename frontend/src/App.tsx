import { Route, Routes } from "react-router";

import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { AdminPage } from "./pages/AdminPage";
import { ComparePage } from "./pages/ComparePage";
import { HealthPage } from "./pages/HealthPage";
import { LoginPage } from "./pages/LoginPage";
import { RunPage } from "./pages/RunPage";
import { ScenarioEditorPage } from "./pages/ScenarioEditorPage";
import { ScenariosPage } from "./pages/ScenariosPage";
import { StudyAreaPage } from "./pages/StudyAreaPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="health" element={<HealthPage />} />
        <Route
          index
          element={
            <RequireAuth>
              <StudyAreaPage />
            </RequireAuth>
          }
        />
        <Route
          path="scenarios"
          element={
            <RequireAuth>
              <ScenariosPage />
            </RequireAuth>
          }
        />
        <Route
          path="scenarios/new"
          element={
            <RequireAuth>
              <ScenarioEditorPage />
            </RequireAuth>
          }
        />
        <Route
          path="scenarios/:scenarioId"
          element={
            <RequireAuth>
              <ScenarioEditorPage />
            </RequireAuth>
          }
        />
        <Route
          path="runs/:runId"
          element={
            <RequireAuth>
              <RunPage />
            </RequireAuth>
          }
        />
        <Route
          path="runs/:runId/compare"
          element={
            <RequireAuth>
              <ComparePage />
            </RequireAuth>
          }
        />
        <Route
          path="admin"
          element={
            <RequireAuth admin>
              <AdminPage />
            </RequireAuth>
          }
        />
      </Route>
    </Routes>
  );
}
