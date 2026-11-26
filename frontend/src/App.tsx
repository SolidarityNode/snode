import type { ReactNode } from "react";
import { Route, Routes } from "react-router";

import { useSession } from "./app/session";

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
import { HubCoveragePage } from "./pages/hub/HubCoveragePage";
import { HubChangesetPage, HubFacilitiesPage } from "./pages/hub/HubFacilitiesPage";
import { HubFacilityPage } from "./pages/hub/HubFacilityPage";
import { HubMunicipalityPage } from "./pages/hub/HubMunicipalityPage";
import { HubOnboardingPage } from "./pages/hub/HubOnboardingPage";
import { HubSourcesPage } from "./pages/hub/HubSourcesPage";
import { HubStudyAreasPage } from "./pages/hub/HubStudyAreasPage";

const auth = (element: ReactNode) => <RequireAuth>{element}</RequireAuth>;

/** Screens of the hub (DEPLOYMENT_MODE=hub, ADR 0012). */
function hubRoutes() {
  return (
    <>
      <Route index element={auth(<HubOnboardingPage />)} />
      <Route path="onboarding/:municipalityId" element={auth(<HubMunicipalityPage />)} />
      <Route path="sources" element={auth(<HubSourcesPage />)} />
      <Route path="coverage" element={auth(<HubCoveragePage />)} />
      <Route path="facilities" element={auth(<HubFacilitiesPage />)} />
      <Route path="facilities/:facilityId" element={auth(<HubFacilityPage />)} />
      <Route path="changesets/:changesetId" element={auth(<HubChangesetPage />)} />
      <Route path="study-areas" element={auth(<HubStudyAreasPage />)} />
    </>
  );
}

export function App() {
  const { config } = useSession();
  const hub = config?.deployment_mode === "hub";
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="health" element={<HealthPage />} />
        {hub && hubRoutes()}
        {!hub && (
          <Route
            index
            element={
              <RequireAuth>
                <StudyAreaPage />
              </RequireAuth>
            }
          />
        )}
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
